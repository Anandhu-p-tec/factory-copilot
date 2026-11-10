"""FastAPI service: /api/ask, /api/docs, /api/health, /pdf/<file>, and the static mobile UI."""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from .answer import build_response, llm_api_key, MODEL
from .ingest import load_corpus
from .retrieval import Index

DOCS_DIR = Path(os.getenv("FC_DOCS_DIR", str(ROOT / "docs"))).resolve()
LOG_PATH = ROOT / "logs" / "queries.jsonl"

SAMPLES = [
    "What is the recommended coolant concentration for the TX-200 CNC turning centre?",
    "The machine is showing alarm AL-104. What does it mean and what should the operator do?",
    "Who is allowed to remove a lockout lock from a machine?",
    "What is the outer diameter tolerance for the BH-220 bearing housing?",
    "How often should spindle runout be checked, and who does it?",
]

app = FastAPI(title="Factory Copilot")
infos, chunks = load_corpus(DOCS_DIR)
index = Index(chunks) if chunks else None
REV_RE = re.compile(r"\brev(?:ision)?\.?\s*0?(\d+)\b", re.I)


class Ask(BaseModel):
    question: str


@app.get("/api/health")
def health():
    return {
        "ok": index is not None,
        "embedder": index.embedder.name if index else None,
        "documents": len(infos),
        "chunks": len(chunks),
        "llm_configured": bool(llm_api_key()),
        "llm_model": MODEL,
    }


@app.get("/api/docs")
def docs():
    return [i.__dict__ for i in infos]


@app.get("/api/samples")
def samples():
    return SAMPLES


@app.post("/api/ask")
def ask(body: Ask):
    q = body.question.strip()
    if not q:
        raise HTTPException(400, "Please type a question.")
    if len(q) > 500:
        raise HTTPException(400, "Question is too long (500 characters max).")
    if index is None:
        raise HTTPException(503, "No documents are loaded. Put PDFs in the docs/ folder and restart.")
    t0 = time.perf_counter()
    m = REV_RE.search(q)
    r = index.search(q, include_revision=int(m.group(1)) if m else None)
    resp = build_response(q, r)
    if m and resp["status"] != "none":
        resp["warnings"].insert(0, f"You asked about Rev {m.group(1)}. Older revisions may be superseded — confirm which revision is in force.")
    resp["latency_ms"] = round((time.perf_counter() - t0) * 1000)
    if os.getenv("FC_LOG", "1") == "1":
        try:
            LOG_PATH.parent.mkdir(exist_ok=True)
            with LOG_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "t": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "q": q,
                    "status": resp["status"],
                    "mode": resp["answer_mode"],
                    "ms": resp["latency_ms"],
                    "src": [f"{s['doc_no']} {s['revision']} p{s['page']}" for s in resp["sources"] if s["role"] == "evidence"],
                }, ensure_ascii=True) + "\n")
        except OSError:
            pass
    return resp


@app.get("/pdf/{name}")
def pdf(name: str):
    safe_name = Path(name).name
    if safe_name != name or safe_name not in {i.file for i in infos}:
        raise HTTPException(404, "Document not found.")
    return FileResponse(DOCS_DIR / safe_name, media_type="application/pdf")


@app.get("/")
def root():
    return FileResponse(ROOT / "static" / "index.html")


app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")
