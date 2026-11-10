<div align="center">

# 🏭 Factory Copilot

### A document-grounded assistant for plant supervisors

**Answers only from controlled SOPs and manuals. Cites the exact document and page. Refuses instead of guessing.**

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![scikit-learn](https://img.shields.io/badge/scikit--learn-TF--IDF-F7931E?logo=scikitlearn&logoColor=white)
![PyMuPDF](https://img.shields.io/badge/PyMuPDF-PDF%20parsing-red)
![Tests](https://img.shields.io/badge/tests-18%20passing-brightgreen)
![LLM](https://img.shields.io/badge/LLM-optional-blueviolet)

[Problem](#-the-problem) · [Features](#-key-features) · [Architecture](#-architecture) · [Demo](#-demo-five-questions) · [Quick Start](#-quick-start) · [Evaluation](#-testing--evaluation) · [Limitations](#-limitations)

</div>

---

## 🎯 The Problem

Maintenance, quality, and safety teams work from long PDF manuals, SOPs, inspection records, and maintenance guides. The information is critical, but finding the **right revision** and confirming the **exact instruction** is slow and error-prone.

In a factory, a confident wrong answer is worse than no answer. Factory Copilot is built around that idea:

| Instead of... | Factory Copilot... |
|---|---|
| Guessing when docs are silent | **Abstains** and says the documents don't answer it |
| Mixing old and new procedures | **Separates current vs superseded** revisions visibly |
| Giving untraceable answers | **Cites document + page** for every answer |
| Depending on an LLM being available | **Falls back to extractive answers** with no API key |

---

## ✨ Key Features

- 📄 **PDF ingestion with page-aware chunking** — indexed at startup
- 🏷️ **Metadata parsing** — document number, revision, effective date, supersession
- 🔎 **Retrieval** — TF-IDF index with identifier-aware matching (e.g. `AL-104`, `TX-200`)
- 🛑 **Safety-oriented abstention** — refuses when the documents don't support an answer
- 🔁 **Revision awareness** — current and superseded versions are clearly separated
- 🤖 **Optional LLM summary mode** — used when a valid API key is configured
- 🧱 **Extractive fallback** — used when no key is set or the model output fails validation
- 📌 **Source and page citations** — in both the API response and the UI
- 🔒 **Protected handling** of unsupported or unsafe questions

---

## 🏗️ Architecture

```mermaid
flowchart LR
    A[PDF documents in docs/] --> B[app.ingest]
    B --> C[page-aware chunks + metadata]
    C --> D[app.retrieval]
    D --> E[relevant evidence + revision checks]
    E --> F[app.answer]
    F --> G[Grounded answer or extractive fallback]
    G --> H[FastAPI API + static frontend]
    H --> I[User browser / phone]
```

### How a question flows

1. **Ingest** — PDFs are parsed with PyMuPDF, split into page-aware chunks, and tagged with revision metadata.
2. **Retrieve** — the question is matched against the TF-IDF index, with extra weight on exact identifiers.
3. **Check** — evidence is scored, superseded documents are separated, and abstention checks decide whether the documents actually answer the question.
4. **Answer** — an LLM summary is generated if a key is configured and validated; otherwise an extractive answer is returned.
5. **Cite** — every response includes the source document and page.

---

## 🎬 Demo: Five Questions

| # | Question | Status | Answer |
|:-:|---|:-:|---|
| 1 | What is the recommended coolant concentration for the TX-200 CNC turning centre? | ✅ Supported | Coolant concentration should be **6 %–8 %**. |
| 2 | The machine is showing alarm AL-104. What does it mean and what should the operator do? | ✅ Supported | AL-104 indicates **low way lube oil level**. Top up with **ISO VG 68** oil to the MAX mark, then press **RESET**. |
| 3 | Who is allowed to remove a lockout lock from a machine? | ✅ Supported | **Only the authorised person who placed the lock** may remove it. Nobody may remove another person's lock. |
| 4 | How many samples must be inspected for a lot of 100 pieces? | ⚠️ Conflict | The **current** plan says **13 samples** must be inspected (a superseded revision exists and is flagged). |
| 5 | What time is the lunch break? | 🚫 None | The loaded documents do not provide a supported answer. |

> **Status legend** — ✅ answered from the documents · ⚠️ multiple revisions found, current one used · 🚫 not in the documents, so the app abstains

---

## 🧰 Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| API | FastAPI, Uvicorn |
| PDF parsing | PyMuPDF |
| Retrieval | scikit-learn (TF-IDF), NumPy |
| Validation | Pydantic |
| Config | python-dotenv |
| LLM (optional) | OpenAI-compatible Groq API |
| Frontend | Static HTML served by FastAPI |

---

## 📁 Project Structure

```text
factory-copilot/
├── app/
│   ├── main.py          # API and startup wiring
│   ├── ingest.py        # PDF parsing, metadata extraction, revision handling
│   ├── retrieval.py     # Search, evidence scoring, abstention checks
│   └── answer.py        # Response generation, validation, extractive fallback
├── static/
│   └── index.html       # Frontend UI
├── tests/
│   └── test_core.py     # Regression tests
├── eval/
│   ├── questions.json   # Evaluation questions
│   └── run_eval.py      # Automated answer evaluation
├── docs/                # Plant documents used by the app
├── README.md            # Project overview and usage
├── THINKING.md          # Design rationale and reflection
└── EVAL.md              # Evaluation results
```

---

## 🚀 Quick Start

> Verified on **Windows 10/11 with PowerShell**.

### 1. Check Python (3.12 or newer)

```powershell
py -3.12 --version
```

### 2. Create and activate a virtual environment

```powershell
cd factory-copilot
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 4. Configure environment variables

```powershell
Copy-Item .env.example .env
notepad .env
```

```env
GROQ_API_KEY=your_groq_api_key_here
FC_MODEL=openai/gpt-oss-120b
```

| Variable | Purpose |
|---|---|
| `GROQ_API_KEY` | Enables LLM summary mode. **Optional** — without it the app uses extractive answers. |
| `FC_MODEL` | Model used for LLM summaries. |

### 5. Run

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then open:

- 💻 http://localhost:8000
- 📱 `http://<your-laptop-ip>:8000` from a phone on the same Wi‑Fi network

---

## 🧪 Testing & Evaluation

```powershell
python -m pytest -q          # regression tests
python eval/run_eval.py      # automated answer evaluation
```

- ✅ **18 tests passing** in the verified environment
- 📊 Evaluation results are documented in [`EVAL.md`](EVAL.md)
- 🧠 Design rationale and trade-offs are documented in [`THINKING.md`](THINKING.md)

---

## ⚠️ Limitations

- Reliability depends on the PDF set in `docs/`; the app is only as good as its source documents.
- Retrieval is local and lightweight, so paraphrase recall may be limited.
- LLM summaries require a valid API key and network access.
- No authentication or user roles are implemented.
- The supplied PDFs are text-faithful stand-ins for the originals; a real deployment should use the controlled documents from the plant QMS or another approved source.

---

## 🔐 Security

- Never commit API keys or secrets.
- Keep keys in a local `.env` file; use `.env.example` as the public template only.
- Do not print tokens or keys in logs or in the README.
- Use a local or controlled LLM endpoint if confidentiality requires it.

---

<div align="center">

**Built for reliability first: if the documents don't say it, Factory Copilot won't either.**

</div>
