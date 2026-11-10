# docs/

Put the plant PDFs here (any file name ending in `.pdf`). They are indexed at startup.

**The four PDFs currently in this folder are text-faithful rebuilds** made by `scripts/build_standin_pdfs.py` from the
text of the originals, because the originals could not be downloaded in the build environment. Before demoing or
submitting, replace them with the real files from the BiztelAI Drive folder (same file names), then run:

    python -m app.ingest docs        # eyeball extraction: metadata, page numbers, chunks
    python eval/run_eval.py          # regenerate EVAL.md against the real PDFs
    python -m pytest -q
