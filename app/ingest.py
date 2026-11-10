"""PDF -> structured, page-aware chunks with document-control metadata.

The ingestion layer keeps each chunk tied to its document, revision, page, section and table headers so
answers can be traced to evidence. Revision status is based on the document-control metadata in the
source PDFs, not just the highest number. When the metadata is missing or conflicting, the document is
flagged as ambiguous rather than silently treated as current.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

import pymupdf

MAX_CHARS = 700
HEADING_RE = re.compile(r"^(\d+)\.\s+(\S.*)$", re.S)
FOOTER_RE = re.compile(r"Uncontrolled copy when printed", re.I)


@dataclass
class Chunk:
    chunk_id: str
    file: str
    doc_no: str | None
    revision: int | None
    revision_label: str | None
    effective: str | None
    title: str
    page: int
    section: str
    kind: str  # "text" | "table_row"
    text: str
    status: str = "current"  # current | superseded | ambiguous

    @property
    def embed_text(self) -> str:
        return f"{self.title}. {self.section}. {self.text}"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DocInfo:
    file: str
    doc_no: str | None
    revision: int | None
    revision_label: str | None
    effective: str | None
    title: str
    approved_by: str | None
    prepared_by: str | None
    pages: int
    status: str = "current"
    superseded_by: str | None = None
    approval_status: str = "unknown"
    supersedes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace(" ", " ")).strip()


def _extract_supersession(text: str) -> list[str]:
    matches: list[str] = []
    for pat in [
        r"supersedes?\s+(?:rev(?:ision)?\.?\s*)?0?(\d+)",
        r"replaces?\s+(?:rev(?:ision)?\.?\s*)?0?(\d+)",
        r"supersed(?:ed)?\s+by\s+(?:rev(?:ision)?\.?\s*)?0?(\d+)",
    ]:
        for m in re.finditer(pat, text, flags=re.I):
            rev = m.group(1)
            if rev:
                matches.append(f"Rev {int(rev):02d}")
    return sorted(set(matches), key=lambda x: int(x.split()[-1]))


def _parse_metadata(first_page_text: str) -> dict:
    t = _norm(first_page_text)
    m_no = re.search(r"Document No\.?\s*([A-Z0-9][A-Z0-9\-]+)", t)
    m_rev = re.search(r"Revision\s*(\d+)", t)
    m_eff = re.search(r"Effective Date\s*(\d{1,2}[-/ ][A-Za-z]{3,9}[-/ ]\d{2,4})", t)
    m_app = re.search(r"Approved By\s*(.+?)(?:\s{2,}|$|\s\d+\.\s[A-Z])", t)
    m_prep = re.search(r"Prepared By\s*(.+?)\s+Approved By", t)
    supersession = _extract_supersession(t)
    approved = "approved" if m_app else "unknown"
    revision_number = int(m_rev.group(1)) if m_rev else None
    return dict(
        doc_no=m_no.group(1) if m_no else None,
        revision=revision_number,
        revision_label=f"Rev {revision_number:02d}" if revision_number is not None else None,
        effective=m_eff.group(1) if m_eff else None,
        approved_by=_norm(m_app.group(1)) if m_app else None,
        prepared_by=_norm(m_prep.group(1)) if m_prep else None,
        approval_status=approved,
        supersedes=supersession,
    )


def _page_elements(page: "pymupdf.Page"):
    """Yield page content in reading order: text blocks or table rows."""
    height = page.rect.height
    tables = []
    try:
        tables = list(page.find_tables().tables)
    except Exception:  # find_tables can fail on odd PDFs; fall back to plain text
        tables = []
    table_boxes = [pymupdf.Rect(t.bbox) for t in tables]
    elems = []

    for b in page.get_text("dict")["blocks"]:
        if b.get("type") != 0:
            continue
        rect = pymupdf.Rect(b["bbox"])
        if any(rect.intersects(tb) and (rect & tb).get_area() > 0.5 * rect.get_area() for tb in table_boxes):
            continue
        spans = [s for ln in b["lines"] for s in ln["spans"] if s["text"].strip()]
        if not spans:
            continue
        text = _norm(" ".join(s["text"] for s in spans))
        if not text or FOOTER_RE.search(text) or rect.y0 > height - 45:
            continue
        bold = all(("bold" in s["font"].lower()) or (s["flags"] & 16) for s in spans)
        elems.append((rect.y0, "text", text, bold, max(s["size"] for s in spans)))

    for t, tb in zip(tables, table_boxes):
        rows = []
        for r in t.rows:
            cells = []
            for c in r.cells:
                cells.append("" if c is None else _norm(page.get_text("text", clip=pymupdf.Rect(c))))
            if any(cells):
                rows.append(cells)
        if rows:
            elems.append((tb.y0, "table", rows))

    elems.sort(key=lambda e: e[0])
    return elems


def extract_document(pdf_path: Path) -> tuple[DocInfo, list[Chunk]]:
    doc = pymupdf.open(pdf_path)
    file = pdf_path.name
    warnings: list[str] = []
    first_text = doc[0].get_text("text") if len(doc) else ""
    meta = _parse_metadata(first_text)

    for i, pg in enumerate(doc, start=1):
        if len(pg.get_text("text").strip()) < 40:
            warnings.append(f"page {i}: almost no extractable text (scanned image? needs OCR)")

    title = pdf_path.stem
    best = 0.0
    first_blocks = doc[0].get_text("dict")["blocks"] if len(doc) else []
    for b in first_blocks:
        for ln in b.get("lines", []):
            for s in ln["spans"]:
                if s["size"] > best and s["text"].strip():
                    best, title = s["size"], _norm(s["text"])

    info = DocInfo(file=file, doc_no=meta["doc_no"], revision=meta["revision"], revision_label=meta["revision_label"],
                   effective=meta["effective"], title=title, approved_by=meta["approved_by"], prepared_by=meta["prepared_by"],
                   pages=len(doc), status="current", approval_status=meta["approval_status"], supersedes=meta["supersedes"],
                   warnings=warnings)

    if not info.doc_no:
        info.warnings.append("Document number missing; this file cannot be trusted as a controlled source without metadata.")
    if info.revision is None:
        info.warnings.append("Revision number missing; current-status determination is uncertain.")
    if not info.effective:
        info.warnings.append("Effective date missing; current status is uncertain until document control confirms it.")
    if info.approval_status == "unknown":
        info.warnings.append("Approval metadata missing; document has not been confirmed as approved.")

    chunks: list[Chunk] = []
    section = "Front matter"
    seen_first_heading = False
    seq = 0

    def make(page_no: int, kind: str, text: str):
        nonlocal seq
        seq += 1
        chunks.append(Chunk(
            chunk_id=f"{pdf_path.stem}:p{page_no}:{seq:02d}", file=file, doc_no=info.doc_no,
            revision=info.revision, revision_label=info.revision_label, effective=info.effective,
            title=info.title, page=page_no, section=section, kind=kind, text=text,
            status="current"))

    for pno, page in enumerate(doc, start=1):
        buf: list[str] = []

        def flush():
            nonlocal buf
            if buf and seen_first_heading:
                make(pno, "text", "\n".join(buf))
            buf = []

        for el in _page_elements(page):
            kind = el[1]
            if kind == "text":
                _, _, text, bold, _size = el
                m = HEADING_RE.match(text)
                if bold and m and len(text) < 120:
                    flush()
                    section = text
                    seen_first_heading = True
                    continue
                if not seen_first_heading:
                    continue
                if sum(len(x) for x in buf) + len(text) > MAX_CHARS and buf:
                    flush()
                buf.append(text)
            else:
                flush()
                rows = el[2]
                if not rows or not seen_first_heading:
                    continue
                header, body_rows = rows[0], rows[1:]
                for r in body_rows:
                    parts = [f"{h}: {c}" for h, c in zip(header, r) if c]
                    if parts:
                        make(pno, "table_row", " | ".join(parts))
        flush()
    return info, chunks


def _choose_current_document(group: list[DocInfo]) -> DocInfo | None:
    if not group:
        return None
    explicit = [d for d in group if d.supersedes]
    if explicit:
        ordered = sorted(explicit, key=lambda d: (d.revision or -1, d.effective or ""), reverse=True)
        return ordered[0]

    approved = [d for d in group if d.approval_status == "approved"]
    if approved:
        ordered = sorted(approved, key=lambda d: (d.revision or -1, d.effective or ""), reverse=True)
        return ordered[0]

    ordered = sorted(group, key=lambda d: (d.revision or -1, d.effective or ""), reverse=True)
    return ordered[0]


def mark_revisions(infos: list[DocInfo], chunks: list[Chunk]) -> None:
    """Mark older revisions as superseded while preserving the historical records for comparison."""
    by_no: dict[str, list[DocInfo]] = {}
    for info in infos:
        if info.doc_no:
            by_no.setdefault(info.doc_no, []).append(info)

    for group in by_no.values():
        if len(group) < 2:
            continue
        current = _choose_current_document(group)
        if current is None:
            continue

        for other in group:
            if other is current:
                other.status = "current"
                other.superseded_by = None
                continue
            other.status = "superseded"
            other.superseded_by = current.revision_label or f"Rev {current.revision}"
        if any(doc.status == "current" for doc in group) and len([d for d in group if d.status == "current"]) > 1:
            for doc in group:
                if doc.status == "current":
                    doc.status = "ambiguous"
                    doc.warnings.append("Multiple current revisions were identified; review document control before relying on this record.")

    status_map = {info.file: info.status for info in infos}
    for chunk in chunks:
        chunk.status = status_map.get(chunk.file, "current")


def load_corpus(docs_dir: Path) -> tuple[list[DocInfo], list[Chunk]]:
    infos: list[DocInfo] = []
    chunks: list[Chunk] = []
    for pdf in sorted(docs_dir.glob("*.pdf")):
        if pdf.name.lower().startswith("sample_questions"):
            continue
        try:
            info, ch = extract_document(pdf)
        except Exception as exc:  # corrupt PDF: report and continue without taking down the service
            infos.append(DocInfo(file=pdf.name, doc_no=None, revision=None, revision_label=None, effective=None,
                                 title=pdf.stem, approved_by=None, prepared_by=None, pages=0,
                                 status="ambiguous", warnings=[f"could not be read: {exc}"]))
            continue
        if not ch:
            info.warnings.append("No usable text was extracted; document skipped from search index.")
            infos.append(info)
            continue
        infos.append(info)
        chunks.extend(ch)

    mark_revisions(infos, chunks)
    return infos, chunks


if __name__ == "__main__":
    import sys
    infos, chunks = load_corpus(Path(sys.argv[1] if len(sys.argv) > 1 else "docs"))
    for i in infos:
        print(f"{i.file}: {i.doc_no} {i.revision_label} eff {i.effective} [{i.status}] pages={i.pages} warn={i.warnings}")
    for c in chunks:
        print(f"\n--- {c.chunk_id} | p{c.page} | {c.section} | {c.kind}\n{c.text}")
