"""
Offline unit tests for the single-job chat relocated to search/ (rework 2.3 #5).

send_job_message is text-only (no Structured Outputs) — it builds a job-scoped system
prompt and returns the model's reply. Inject a fake client to assert the happy path,
session continuity (previous_response_id), and the no-key / error fallbacks, with no network.
"""
import jobs_intelligence_ai.services.search.job_chat as jc_mod
from jobs_intelligence_ai.services.search.job_chat import send_job_message, clear_job_session


class _FakeResponses:
    """`.create()` records the kwargs it was called with and returns a canned reply."""
    def __init__(self, text="ok", exc=None):
        self.text, self.exc, self.calls = text, exc, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        return type("Resp", (), {"id": "resp_123", "output_text": self.text})()


class _FakeClient:
    def __init__(self, text="ok", exc=None):
        self.responses = _FakeResponses(text, exc)


def _patch(monkeypatch, text="ok", exc=None):
    client = _FakeClient(text, exc)
    monkeypatch.setattr(jc_mod, "get_client", lambda *a, **k: client)
    monkeypatch.setattr(jc_mod.config, "OPENAI_API_KEY", "test-key")
    return client


_JOB = {"title": "Backend Engineer", "company": "ACME", "city": "Wien",
        "skills": "Python", "description": "Build APIs."}


def test_no_api_key_returns_message(monkeypatch):
    """With no API key, returns an explanatory message without calling the model."""
    monkeypatch.setattr(jc_mod.config, "OPENAI_API_KEY", "")
    out = send_job_message("s1", "What skills?", _JOB)
    assert "OpenAI API key" in out["text"]


def test_happy_path_returns_reply_and_stores_session(monkeypatch):
    """Returns the model's text and remembers the response id for the next turn."""
    clear_job_session("s1")
    client = _patch(monkeypatch, text="It needs Python.")
    out = send_job_message("s1", "What skills?", _JOB)
    assert out == {"text": "It needs Python."}
    # second turn threads previous_response_id from the stored session
    send_job_message("s1", "And seniority?", _JOB)
    assert client.responses.calls[1]["previous_response_id"] == "resp_123"


def test_candidate_text_is_appended_to_prompt(monkeypatch):
    """A supplied candidate profile is folded into the system instructions for fit."""
    client = _patch(monkeypatch)
    send_job_message("s2", "Is my candidate a fit?", _JOB, candidate_text="10y Python lead")
    assert "10y Python lead" in client.responses.calls[0]["instructions"]


def test_error_is_caught(monkeypatch):
    """A model error degrades to a friendly message instead of raising."""
    _patch(monkeypatch, exc=RuntimeError("boom"))
    out = send_job_message("s3", "hi", _JOB)
    assert "something went wrong" in out["text"]
