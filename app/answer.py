"""Turn a Retrieval into the response shown to the supervisor.

Two modes, same output shape:
  * llm        - a hosted LLM (Groq by default, any OpenAI-compatible endpoint) writes a short answer from the retrieved passages only; the output is validated
                 (JSON schema, citations must exist, every number must appear in a cited passage).
  * extractive - no model: the best passage is shown verbatim. Used when there is no API key, when the
                 API fails/times out, or when validation rejects the model's answer.
The model is never called when retrieval already decided the documents don't answer the question.
"""
from __future__ import annotations

import json
import os
import re
import time

from .retrieval import Hit, Retrieval, numbers, stem, terms

# Groq has a free tier and an OpenAI-compatible API. Any OpenAI-compatible server works (e.g. a local Ollama:
# FC_LLM_BASE_URL=http://localhost:11434/v1). Check console.groq.com/docs/models for currently available free models.
DEFAULT_MODEL = "openai/gpt-oss-120b"
MODEL = os.getenv("FC_MODEL", DEFAULT_MODEL)
BASE_URL = os.getenv("FC_LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
LLM_TIMEOUT_S = float(os.getenv("FC_LLM_TIMEOUT", "20"))

SYSTEM_PROMPT = """You are a manufacturing document assistant for a plant supervisor.

Rules:
- Answer ONLY from the numbered reference passages. Do not use outside knowledge.
- Never invent machine settings, safety steps, maintenance intervals, limits or names.
- Keep it short and plain: at most 4 short sentences, or a short numbered list for procedures.
- If the passages only partly answer the question, state what is answered and what is NOT in the documents.
- If the passages do not answer the question, set status to "none".
- Passages marked SUPERSEDED are old revisions: never answer from them.
- If two current passages give different instructions, set status to "conflict" and describe both.
- Keep numbers, units and part/alarm codes exactly as written in the passages.
- Cite every passage you used by its number.
- Use numbers only if they are explicitly stated in the cited passages.

Reply with JSON only:
{"status": "supported" | "partial" | "none" | "conflict",
 "answer": "<short answer>",
 "used": [<passage numbers>],
 "missing": "<what the documents do not say, or empty>"}"""

RULE_RE = re.compile(r"\b(never|must not|must|do not|mandatory|not allowed|only through|serious safety)\b", re.I)


def _pretty_row(text: str) -> str:
    return "\n".join(p.strip() for p in text.split(" | "))


def _best_lines(question: str, text: str) -> str:
    """Extractive highlight: the lines of a passage that share the most content words with the question."""
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    if len(lines) <= 2:
        return "\n".join(lines)
    q = set(terms(question))
    scored = [(sum(1 for t in set(terms(ln)) if t in q), ln) for ln in lines]
    top = max(sc for sc, _ in scored)
    if top == 0:
        return "\n".join(lines)
    picked, take_rest = [], False
    for sc, ln in scored:
        if take_rest or sc >= max(1, 0.6 * top):
            picked.append(ln)
            if ln.endswith(":"):      # an intro line ("...only through this procedure:") must keep its steps
                take_rest = True
    return "\n".join(picked)


def _source(n: int, h: Hit, used: bool, role: str) -> dict:
    c = h.chunk
    return {
        "n": n, "role": role,  # evidence | superseded | closest
        "used": used, "file": c.file, "title": c.title, "doc_no": c.doc_no, "revision": c.revision_label,
        "effective": c.effective, "doc_status": c.status, "page": c.page, "section": c.section,
        "kind": c.kind, "text": _pretty_row(c.text) if c.kind == "table_row" else c.text,
        "score": round(h.score, 3), "coverage": round(h.coverage, 3),
    }


def _rules_from(hits: list[Hit]) -> list[dict]:
    """Verbatim mandatory/prohibition sentences from the evidence - quoted, never generated."""
    out, seen = [], set()
    for h in hits:
        for sent in re.split(r"(?<=[.!?])\s+|\n", h.chunk.text):
            s = sent.strip(" •-")
            if len(s) > 15 and RULE_RE.search(s) and s not in seen:
                seen.add(s)
                out.append({"text": s, "doc_no": h.chunk.doc_no, "revision": h.chunk.revision_label, "page": h.chunk.page})
    return out[:4]


def _range_row_answer(question: str, ev: list[Hit]) -> str | None:
    """Prefer the matching table row for range questions like '100 pieces' instead of the header row."""
    q_nums = sorted(numbers(question), key=lambda x: len(x))
    if not q_nums:
        return None
    for h in ev:
        if h.chunk.kind != "table_row":
            continue
        row = _pretty_row(h.chunk.text)
        for qn in q_nums:
            try:
                target = int(qn.replace(",", ""))
            except ValueError:
                continue
            for start, end in re.findall(r"(\d[\d,\.]*)\s*-\s*(\d[\d,\.]*)", row):
                try:
                    lo = int(start.replace(",", ""))
                    hi = int(end.replace(",", ""))
                except ValueError:
                    continue
                if lo <= target <= hi:
                    match = re.search(r"(?:Samples to inspect|Samples? required|Sample count|Inspect(?:ion)? count)\s*[:\-]?\s*(\d[\d,\.]*)", row, re.I)
                    if match:
                        return f"For a lot of {qn} pieces, the current plan says {match.group(1)} samples must be inspected."
                    return f"For a lot of {qn} pieces, the matching table row is: {row}"
    return None


def llm_api_key() -> str | None:
    return os.getenv("GROQ_API_KEY") or os.getenv("FC_LLM_API_KEY")


def _post_chat(payload: dict) -> dict:
    import httpx

    r = httpx.post(f"{BASE_URL}/chat/completions", json=payload, timeout=LLM_TIMEOUT_S,
                   headers={"Authorization": f"Bearer {llm_api_key()}", "Content-Type": "application/json"})
    r.raise_for_status()
    return r.json()


def _llm_answer(question: str, ev: list[Hit]) -> dict | None:
    """Returns validated dict or raises. None if no API key."""
    if not llm_api_key():
        return None
    passages = "\n\n".join(
        f"[{i}] {h.chunk.doc_no} {h.chunk.revision_label} (effective {h.chunk.effective}), page {h.chunk.page}, "
        f"section \"{h.chunk.section}\"\n{h.chunk.text}" for i, h in enumerate(ev, start=1))
    payload = {
        "model": MODEL,
        "temperature": 0,
        "max_tokens": 600,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": f"Question: {question}\n\nReference passages:\n\n{passages}"}],
    }
    try:
        resp = _post_chat(payload)
    except Exception:
        if MODEL != DEFAULT_MODEL:
            payload["model"] = DEFAULT_MODEL
            resp = _post_chat(payload)
        else:
            raise
    raw = (resp["choices"][0]["message"]["content"] or "").strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    if not raw:
        raise ValueError("empty LLM response")
    try:
        payload_json = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON response: {exc}") from exc
    return validate_llm(payload_json, question, ev)


def validate_llm(data: dict, question: str, ev: list[Hit]) -> dict:
    """Reject anything that is not traceable to the retrieved passages."""
    if not isinstance(data, dict):
        raise ValueError("LLM response is not a JSON object")
    if data.get("status") not in {"supported", "partial", "none", "conflict"}:
        raise ValueError("bad status")
    answer = str(data.get("answer", "")).strip()
    raw_used = data.get("used", [])
    if not isinstance(raw_used, list):
        raise ValueError("used must be a list of citation numbers")
    used: list[int] = []
    for u in raw_used:
        if isinstance(u, bool) or not isinstance(u, int):
            raise ValueError("citation indexes must be integers")
        if u < 1 or u > len(ev):
            raise ValueError("citation to a passage that was not provided")
        used.append(u)
    if data["status"] != "none":
        if not answer:
            raise ValueError("answer missing")
        if not used:
            raise ValueError("answer without citations")
        cited_text = " ".join(ev[u - 1].chunk.text for u in used)
        allowed = numbers(cited_text)
        ungrounded = sorted(n for n in numbers(answer) if n not in allowed)
        if ungrounded:
            raise ValueError(f"numbers not found in cited passages: {ungrounded}")
    return {"status": data["status"], "answer": answer, "used": used, "missing": str(data.get("missing", "")).strip()}


def build_response(question: str, r: Retrieval, force_extractive: bool = False) -> dict:
    t0 = time.perf_counter()
    notes = list(r.notes)
    warnings: list[str] = []
    sources: list[dict] = []
    answer_mode = "none"
    answer = ""
    status = r.status
    missing = ""

    if r.status == "none":
        answer = "The loaded documents do not give a supported answer to this question. Do not rely on this tool for it — check with your supervisor, maintenance or the document owner."
        sources = [_source(i, h, False, "closest") for i, h in enumerate(r.closest, start=1)]
        if sources:
            notes.append("Closest text found is shown for reference only. It does not answer the question.")
    else:
        ev = r.evidence
        used_idx: set[int] = set(range(1, len(ev) + 1))
        llm = None
        matched_range_answer = _range_row_answer(question, ev) if r.unmatched_numbers else None
        if matched_range_answer and not force_extractive:
            answer_mode = "extractive"
            answer = matched_range_answer
            sources = [_source(i, h, True, "evidence") for i, h in enumerate(ev, start=1)]
            if not any("AI summary" in n for n in notes):
                notes.append("Showing the matched table row directly for this range/limit question.")
        else:
            if not force_extractive:
                try:
                    llm = _llm_answer(question, ev)
                except Exception as e:  # network down, timeout, bad JSON, failed validation -> safe fallback
                    notes.append(f"AI summary unavailable ({type(e).__name__}); showing the document text directly.")
            if llm and llm["status"] == "none":
                status, answer, answer_mode = "none", "The documents do not give a supported answer to this question.", "llm"
                sources = [_source(i, h, False, "closest") for i, h in enumerate(ev[:2], start=1)]
                missing = llm["missing"]
            elif llm:
                answer_mode, answer, missing = "llm", llm["answer"], llm["missing"]
                used_idx = set(llm["used"])
                if llm["status"] in ("partial", "conflict") and status == "supported":
                    status = llm["status"]
                elif llm["status"] == "conflict":
                    status = "conflict"
                sources = [_source(i, h, i in used_idx, "evidence") for i, h in enumerate(ev, start=1)]
            else:
                answer_mode = "extractive"
                if r.unmatched_numbers:
                    # A threshold/range lookup: picking one row would look like an answer but could be the wrong row.
                    answer = ("This depends on a value the documents give as a range or limit (" + ", ".join(r.unmatched_numbers)
                              + "). The relevant table is listed under Sources — find the matching row and read it yourself.")
                else:
                    parts = []
                    for i, h in enumerate(ev[:2], start=1):
                        body = _pretty_row(h.chunk.text) if h.chunk.kind == "table_row" else _best_lines(question, h.chunk.text)
                        parts.append(f"[{i}] {body}")
                    answer = "\n\n".join(parts)
                sources = [_source(i, h, True, "evidence") for i, h in enumerate(ev, start=1)]
                if answer_mode == "extractive" and not any("AI summary" in n for n in notes):
                    notes.append("Showing the document text directly (no AI summary configured).")

        if r.superseded:
            base = len(sources)
            sources += [_source(base + i, h, False, "superseded") for i, h in enumerate(r.superseded, start=1)]
            old = r.superseded[0].chunk
            cur = ev[0].chunk if ev else None
            msg = (f"An older revision ({old.revision_label}, effective {old.effective}) also matches this question. "
                   f"It is SUPERSEDED" + (f" by {cur.revision_label} (effective {cur.effective})" if cur else "") +
                   " — follow the current revision only.")
            if r.revision_conflict:
                msg += " The two revisions give different values, so confirm in the QMS before acting."
                status = "conflict" if status in ("supported", "partial") else status
            warnings.append(msg)
        if status != "none":
            rules = _rules_from([h for h in ev if h.coverage > 0 or h.score > 0] or ev)
        else:
            rules = []
    if r.status == "none":
        rules = []

    return {
        "question": question, "status": status, "answer": answer, "answer_mode": answer_mode,
        "missing": missing, "warnings": warnings, "notes": notes, "rules": rules, "sources": sources,
        "diagnostics": {"best_coverage": r.best_coverage, "best_score": r.best_score,
                        "unmatched_numbers": r.unmatched_numbers},
        "answer_ms": round((time.perf_counter() - t0) * 1000),
    }
