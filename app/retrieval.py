"""Retrieval + evidence check.

The evidence check is intentionally independent of the embedder and LLM. A similarity score alone
cannot tell a relevant chunk from a misleading one; coverage of the query's content words and the
presence of matching machine/alarm identifiers are used to separate evidence from noise.
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field

try:
    import faiss
except Exception:  # pragma: no cover - fallback for some Windows environments
    faiss = None
import numpy as np

from .ingest import Chunk

# ---- tunables (set against eval/questions.json; see EVAL.md) ----
TOP_K = 8
COV_ABSTAIN = 0.65
COV_FULL = 0.80
IDENT_FLOOR = 0.70
IDENT_BOOST = 0.5
COV_WEIGHT = 0.4
REL_KEEP = 0.70
COV_KEEP = 0.70
MAX_EVIDENCE = 4

STOP = set("""a an the of for to in on at by with from and or but if is are was were be been am do does did can could should
would will shall may might must what which who whom whose when where why how often much many i my we our you your me us it its this
that these those there here please tell show give about into than then so as not no any all some per also
mean means meant recommended allowed permitted
show shows showing shown say says said see seeing display displays displayed get getting happen happens happening
need needs want let know find tell have has had make made""".split())

SYNONYMS = {
    "disconnect": ["isolate", "isolator"],
    "unplug": ["isolate"],
    "power": ["electrical", "energy"],
    "loto": ["lockout", "tagout"],
    "padlock": ["lock", "lockout"],
    "lock": ["padlock", "lockout"],
    "lockout": ["padlock", "lock"],
    "unlock": ["remove", "lock"],
    "remove": ["take", "detach", "unfasten", "takeoff", "take-off"],
    "take": ["remove", "detach", "takeoff", "take-off"],
    "takeoff": ["remove", "detach"],
    "take-off": ["remove", "detach"],
    "off": ["remove", "detach"],
    "oil": ["hydraulic", "lube"],
    "fix": ["replace"],
    "arrive": ["receive"],
    "arrived": ["received"],
    "delivered": ["received"],
    "someone": ["other", "another", "person"],
    "else": ["other", "another"],
    "owner": ["person", "operator", "employee"],
    "person": ["operator", "employee", "owner"],
    "their": ["own"],
    "own": ["their"],
    "installed": ["install", "installer"],
    "install": ["installed"],
}

IDENT_RE = re.compile(r"\b[A-Za-z]{1,6}(?:-[A-Za-z]{1,6})*-?\d{1,4}[A-Za-z]?\b")
WORD_RE = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")
NUM_RE = re.compile(r"(?<![A-Za-z\-])\d+(?:[.,]\d+)?")


def stem(w: str) -> str:
    for suf in ("ions", "ion", "ings", "ing", "edly", "ed", "ies", "es", "s", "ly", "e"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)]
    return w


SYNONYMS = {stem(k): sorted(set(v)) for k, v in SYNONYMS.items()}


def idents(text: str) -> set[str]:
    out = set()
    for m in IDENT_RE.findall(text):
        if re.search(r"[A-Za-z]", m) and re.search(r"\d", m):
            out.add(re.sub(r"[^A-Z0-9]", "", m.upper()))
    return out


def terms(text: str) -> list[str]:
    """Stemmed content words of a text (identifiers are handled separately)."""
    cleaned = IDENT_RE.sub(" ", text)
    return [stem(w) for w in WORD_RE.findall(cleaned.lower()) if w not in STOP and not w.isdigit()]


def numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in NUM_RE.findall(IDENT_RE.sub(" ", text))}


class TfidfEmbedder:
    """Local, offline, dependency-light. Good at exact/near-exact vocabulary and phrase-level safety text."""
    name = "tfidf"

    def __init__(self, texts: list[str]):
        from sklearn.feature_extraction.text import TfidfVectorizer

        self.vec = TfidfVectorizer(analyzer=self._analyze, sublinear_tf=True, norm="l2")
        self.vec.fit(texts)

    @staticmethod
    def _analyze(text: str) -> list[str]:
        t = terms(text)
        expanded = []
        for word in t:
            expanded.append(word)
            for alt in SYNONYMS.get(word, []):
                expanded.append(alt)
        return expanded + [f"{a}_{b}" for a, b in zip(t, t[1:])] + sorted(idents(text))

    def encode(self, texts: list[str], query: bool = False) -> np.ndarray:
        return self.vec.transform(texts).toarray().astype("float32")


class SentenceTransformerEmbedder:
    """Optional semantic embedder; not required for the local, safe default."""
    name = "sentence-transformers"

    def __init__(self, model: str):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model)
        self.name = f"sentence-transformers:{model}"

    def encode(self, texts: list[str], query: bool = False) -> np.ndarray:
        if query and "bge" in self.name.lower():
            texts = ["Represent this sentence for searching relevant passages: " + t for t in texts]
        return self.model.encode(texts, normalize_embeddings=True).astype("float32")


def make_embedder(texts: list[str]):
    if os.getenv("FC_EMBEDDER", "tfidf").lower() == "st":
        try:
            return SentenceTransformerEmbedder(os.getenv("FC_EMBED_MODEL", "BAAI/bge-small-en-v1.5"))
        except Exception as exc:  # missing package / no network and no cache
            print(f"[retrieval] sentence-transformers unavailable ({exc}); falling back to TF-IDF")
    return TfidfEmbedder(texts)


@dataclass
class Hit:
    chunk: Chunk
    score: float
    coverage: float


@dataclass
class Retrieval:
    status: str
    evidence: list[Hit] = field(default_factory=list)
    superseded: list[Hit] = field(default_factory=list)
    revision_conflict: bool = False
    notes: list[str] = field(default_factory=list)
    best_coverage: float = 0.0
    best_score: float = 0.0
    unmatched_numbers: list[str] = field(default_factory=list)
    closest: list[Hit] = field(default_factory=list)


class Index:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        texts = [c.embed_text for c in chunks]
        self.embedder = make_embedder(texts)
        mat = self.embedder.encode(texts)

        if faiss is not None and mat.size:
            self.index = faiss.IndexFlatIP(mat.shape[1])
            self.index.add(mat)
            self._fallback = False
        else:
            self.index = None
            self._fallback = True
            self._matrix = mat

        self.chunk_terms = [set(terms(t)) for t in texts]
        self.chunk_idents = [idents(t) for t in texts]
        self.chunk_body_idents = [idents(c.text) for c in chunks]
        self.chunk_numbers = [numbers(c.text) for c in chunks]
        df: dict[str, int] = {}
        for ts in self.chunk_terms:
            for t in ts:
                df[t] = df.get(t, 0) + 1
        n = len(chunks)
        self.idf = {t: math.log((n + 1) / (d + 0.5)) + 1 for t, d in df.items()}
        self.idf_unseen = math.log(n + 1) + 1.5
        self.all_idents = set().union(*self.chunk_idents) if self.chunk_idents else set()

    def _score_query(self, qv: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if self.index is not None:
            scores, ids = self.index.search(qv, min(len(self.chunks), 256))
            return scores[0], ids[0]
        sims = self._matrix @ qv[0]
        order = np.argsort(sims)[::-1][:min(len(self.chunks), 256)]
        return sims[order], order

    def _coverage(self, q_terms: list[str], q_idents: set[str], i: int) -> float:
        have = self.chunk_terms[i]
        total = covered = 0.0
        for t in set(q_terms):
            w = self.idf.get(t, self.idf_unseen)
            total += w
            alts = [t] + [stem(s) for s in SYNONYMS.get(t, [])]
            if any(a in have for a in alts):
                covered += w
        for idt in q_idents:
            w = self.idf_unseen
            total += w
            if idt in self.chunk_idents[i]:
                covered += w
        cov = covered / total if total else 0.0
        if q_idents & self.chunk_body_idents[i]:
            cov = max(cov, IDENT_FLOOR)
        return cov

    def search(self, question: str, include_revision: int | None = None) -> Retrieval:
        q_idents = idents(question)
        q_terms = terms(question)
        expanded_terms = set(q_terms)
        lowered = question.lower()
        if re.search(r"(take|remove|detach).*?(padlock|lockout|lock)", lowered) or re.search(r"(padlock|lockout|lock).*(someone|another|other|person)", lowered):
            expanded_terms |= {"take", "remove", "detach", "padlock", "lock", "lockout", "person", "operator", "employee", "owner", "install", "installed", "own", "their"}
        for w in q_terms:
            expanded_terms |= {stem(s) for s in SYNONYMS.get(w, [])}
        expanded = question + " " + " ".join(sorted(expanded_terms))

        if not q_terms and not q_idents:
            return Retrieval("none", notes=["The question has no searchable content."])

        unknown = sorted(i for i in q_idents if i not in self.all_idents)
        if unknown:
            return Retrieval("none", notes=[f"“{u}” is not mentioned in any loaded document." for u in unknown])

        qv = self.embedder.encode([expanded], query=True)
        scores, ids = self._score_query(qv)
        hits: list[Hit] = []
        for s, i in zip(scores, ids):
            if i < 0:
                continue
            boost = IDENT_BOOST if q_idents & self.chunk_idents[int(i)] else 0.0
            cov = self._coverage(q_terms, q_idents, int(i))
            hits.append(Hit(self.chunks[int(i)], float(s) + boost + COV_WEIGHT * cov, cov))
        hits.sort(key=lambda h: h.score, reverse=True)
        if not hits:
            return Retrieval("none", notes=["Nothing relevant was found in the documents."])

        def usable(h: Hit) -> bool:
            return h.chunk.status == "current" or (include_revision is not None and h.chunk.revision == include_revision)

        current = [h for h in hits if usable(h)][:TOP_K]
        old = [h for h in hits if not usable(h)]
        ref_pool = current or old
        best = ref_pool[0]
        best_cov = max(h.coverage for h in ref_pool[:3])
        r = Retrieval("none", best_coverage=round(best_cov, 3), best_score=round(best.score, 3))

        orig: dict[str, str] = {}
        for w in WORD_RE.findall(IDENT_RE.sub(" ", question).lower()):
            orig.setdefault(stem(w), w)
        unseen = sorted({t for t in q_terms if t not in self.idf and not any(stem(x) in self.idf for x in SYNONYMS.get(t, []))})
        if unseen:
            r.notes.append("The documents never mention: " + ", ".join(f"“{orig.get(t, t)}”" for t in unseen) + ".")

        if best_cov < COV_ABSTAIN:
            r.notes.append("The closest passages do not address the main terms of the question.")
            r.closest = ref_pool[:2]
            return r

        keep = [h for h in current if h.score >= REL_KEEP * best.score and h.coverage >= COV_KEEP * best_cov][:MAX_EVIDENCE]
        r.evidence = keep
        r.status = "supported" if best_cov >= COV_FULL else "partial"
        if r.status == "partial":
            r.notes.append("Only part of the question is covered by the documents.")

        ev_numbers = set().union(*[numbers(h.chunk.text) for h in keep]) if keep else set()
        r.unmatched_numbers = sorted(n for n in numbers(question) if n not in ev_numbers)
        if r.unmatched_numbers:
            r.evidence = self._expand_tables(keep)
            if r.status == "supported":
                r.status = "partial"
            r.notes.append("Your question mentions " + ", ".join(r.unmatched_numbers)
                           + ", which the documents do not state directly - check the limits/table yourself.")
        keep = r.evidence

        ev_files = {h.chunk.file for h in keep}
        ev_docnos = {h.chunk.doc_no for h in keep}
        r.superseded = [h for h in old if h.chunk.doc_no in ev_docnos and h.chunk.file not in ev_files and h.coverage >= 0.5][:2]
        if r.superseded:
            ev_text = " ".join(h.chunk.text for h in keep)
            old_text = " ".join(h.chunk.text for h in r.superseded)
            differs = (numbers(old_text) - numbers(ev_text)) or (idents(old_text) - idents(ev_text))
            r.revision_conflict = bool(differs)
        return r

    def _expand_tables(self, keep: list[Hit]) -> list[Hit]:
        out: list[Hit] = []
        have: set[str] = set()
        for h in keep:
            if h.chunk.chunk_id not in have:
                out.append(h)
                have.add(h.chunk.chunk_id)
            if h.chunk.kind != "table_row":
                continue
            siblings = [c for c in self.chunks if c.kind == "table_row" and c.file == h.chunk.file and c.section == h.chunk.section and c.page == h.chunk.page]
            if len(siblings) <= 8:
                for c in siblings:
                    if c.chunk_id not in have:
                        out.append(Hit(c, 0.0, 0.0))
                        have.add(c.chunk_id)
        return out
