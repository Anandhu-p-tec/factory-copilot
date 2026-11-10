"""Core behaviour tests. Run: python -m pytest -q
The LLM is faked: these tests check OUR guard-rails (validation, fallback, abstention), not the model."""
import os, sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["FC_LOG"] = "0"
os.environ.pop("GROQ_API_KEY", None)
os.environ.pop("FC_LLM_API_KEY", None)

from fastapi.testclient import TestClient
from app import answer as A
from app.main import app, index, infos
from app.retrieval import Hit

client = TestClient(app)


def ask(q):
    return client.post("/api/ask", json={"question": q}).json()


def test_metadata_and_revision_status():
    by = {i.file: i for i in infos}
    r3 = by["QC-SOP-014_Rev03_Incoming_Material_Inspection.pdf"]
    r4 = by["QC-SOP-014_Rev04_Incoming_Material_Inspection.pdf"]
    assert (r3.doc_no, r3.revision, r3.status, r3.superseded_by) == ("QC-SOP-014", 3, "superseded", "Rev 04")
    assert (r4.revision, r4.effective, r4.status) == (4, "01-Jul-2026", "current")
    assert all(not i.warnings for i in infos)


def test_page_numbers_are_correct():
    d = ask("The machine is showing alarm AL-104. What does it mean?")
    assert d["status"] == "supported"
    s = d["sources"][0]
    assert (s["doc_no"], s["page"]) == ("MNT-MAN-CNC-02", 2) and "Way lube oil level low" in s["text"]


def test_unknown_identifier_abstains_without_guessing():
    d = ask("What does alarm AL-999 mean?")
    assert d["status"] == "none" and not [s for s in d["sources"] if s["role"] == "evidence"]
    d = ask("What is the coolant concentration for the TX-300?")   # wrong model must not reuse TX-200 values
    assert d["status"] == "none"


def test_unanswerable_is_refused():
    for q in ["What should I check if the machine overheats?", "What is the recommended spindle speed for the TX-200?"]:
        assert ask(q)["status"] == "none"


def test_superseded_revision_never_used_as_evidence():
    d = ask("How many samples must be inspected for a lot of 100 pieces?")
    ev = [s for s in d["sources"] if s["role"] == "evidence"]
    assert ev and all(s["revision"] == "Rev 04" for s in ev)
    assert any(s["role"] == "superseded" and s["revision"] == "Rev 03" for s in d["sources"])
    assert d["warnings"] and "SUPERSEDED" in d["warnings"][0]
    assert d["status"] in ("partial", "conflict")
    assert "100" in d["answer"] and "Lot size" not in d["answer"]   # must not headline an arbitrary table row


def test_pdf_endpoint_blocks_traversal():
    assert client.get("/pdf/..%2F..%2Fetc%2Fpasswd").status_code == 404
    assert client.get("/pdf/SAF-SOP-003_Lockout_Tagout_Procedure.pdf").status_code == 200


def test_input_validation():
    assert client.post("/api/ask", json={"question": "  "}).status_code == 400
    assert client.post("/api/ask", json={"question": "x" * 501}).status_code == 400


# ---- LLM guard-rails (fake model) ----
def _hits():
    r = index.search("What is the recommended coolant concentration for the TX-200 CNC turning centre?")
    return r, r.evidence


def test_validate_rejects_invented_number():
    r, ev = _hits()
    bad = {"status": "supported", "answer": "Keep it at 7 - 9 %.", "used": [1]}
    with pytest.raises(ValueError):
        A.validate_llm(bad, "coolant?", ev)


def test_validate_rejects_missing_or_bad_citation():
    r, ev = _hits()
    with pytest.raises(ValueError):
        A.validate_llm({"status": "supported", "answer": "6 - 8 %", "used": []}, "q", ev)
    with pytest.raises(ValueError):
        A.validate_llm({"status": "supported", "answer": "6 - 8 %", "used": [99]}, "q", ev)


def test_validate_rejects_question_numbers_not_in_cited_evidence():
    _, ev = _hits()
    with pytest.raises(ValueError):
        A.validate_llm({"status": "supported", "answer": "The coolant should be 100 %.", "used": [1]}, "What is the coolant concentration for 100 percent coolant?", ev)


def test_paraphrased_lockout_question_is_supported():
    d = ask("Who can take off someone else's padlock?")
    assert d["status"] == "supported"
    assert any("removes only their own lock" in s["text"].lower() for s in d["sources"] if s["role"] == "evidence")


def test_missing_api_key_works_in_extractive_mode(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("FC_LLM_API_KEY", raising=False)
    assert A.llm_api_key() is None
    d = ask("What is the recommended coolant concentration for the TX-200 CNC turning centre?")
    assert d["answer_mode"] in {"extractive", "llm"}


def test_valid_llm_answer_is_used(monkeypatch):
    r, ev = _hits()
    monkeypatch.setattr(A, "_llm_answer", lambda q, e: A.validate_llm(
        {"status": "supported", "answer": "Coolant concentration should be 6 - 8 %.", "used": [1], "missing": ""}, q, e))
    d = A.build_response("What is the coolant concentration?", r)
    assert d["answer_mode"] == "llm" and d["answer"].startswith("Coolant")
    assert d["sources"][0]["used"] is True


def test_llm_failure_falls_back_to_document_text(monkeypatch):
    r, ev = _hits()
    def boom(q, e): raise TimeoutError("api down")
    monkeypatch.setattr(A, "_llm_answer", boom)
    d = A.build_response("coolant?", r)
    assert d["answer_mode"] == "extractive" and "6 - 8 %" in d["answer"]
    assert any("unavailable" in n for n in d["notes"])


def test_llm_saying_none_is_respected(monkeypatch):
    r, ev = _hits()
    monkeypatch.setattr(A, "_llm_answer", lambda q, e: {"status": "none", "answer": "", "used": [], "missing": "x"})
    assert A.build_response("coolant?", r)["status"] == "none"


def test_model_is_not_called_when_retrieval_abstains(monkeypatch):
    called = []
    monkeypatch.setattr(A, "_llm_answer", lambda q, e: called.append(1))
    r = index.search("What does alarm AL-999 mean?")
    A.build_response("What does alarm AL-999 mean?", r)
    assert not called


def test_groq_request_and_response_shape(monkeypatch):
    """OpenAI-compatible chat call: correct payload out, JSON content in, then validated."""
    sent = {}
    def fake_post(payload):
        sent.update(payload)
        return {"choices": [{"message": {"content": '{"status":"supported","answer":"6 - 8 %","used":[1],"missing":""}'}}]}
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(A, "_post_chat", fake_post)
    r, ev = _hits()
    out = A._llm_answer("coolant concentration?", ev)
    assert out["status"] == "supported" and out["used"] == [1]
    assert sent["messages"][0]["role"] == "system" and sent["response_format"] == {"type": "json_object"}
    assert "Reference passages" in sent["messages"][1]["content"] and "6 - 8 %" in sent["messages"][1]["content"]


def test_groq_bad_json_falls_back(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(A, "_post_chat", lambda p: {"choices": [{"message": {"content": "Sure! The answer is 7 %"}}]})
    r, ev = _hits()
    d = A.build_response("coolant?", r)
    assert d["answer_mode"] == "extractive" and any("unavailable" in n for n in d["notes"])
