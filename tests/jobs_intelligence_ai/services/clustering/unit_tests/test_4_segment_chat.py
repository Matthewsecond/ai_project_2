"""
Offline unit tests for the segment chat relocated to clustering/ (2.3 #6).

send_segment_message is text-only (no Structured Outputs): it builds a segment-scoped
system prompt and returns the model's reply. Inject a fake client to assert the happy path,
session continuity (previous_response_id), and the no-key / error fallbacks, with no network.
"""
import jobs_intelligence_ai.services.clustering.segment_chat as sc_mod
from jobs_intelligence_ai.services.clustering import send_segment_message, clear_segment_session


class _FakeResponses:
    """`.create()` records its kwargs and returns a canned reply with an id."""
    def __init__(self, text="ok", exc=None):
        self.text, self.exc, self.calls = text, exc, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        return type("Resp", (), {"id": "resp_1", "output_text": self.text})()


class _FakeClient:
    def __init__(self, text="ok", exc=None):
        self.responses = _FakeResponses(text, exc)


def _patch(monkeypatch, text="ok", exc=None):
    client = _FakeClient(text, exc)
    monkeypatch.setattr(sc_mod, "get_client", lambda *a, **k: client)
    monkeypatch.setattr(sc_mod.config, "OPENAI_API_KEY", "test-key")
    return client


_SEG = {"title": "Senior sellers", "summary": "Enterprise AEs",
        "persona_text": "10y SaaS sales", "members": [{"name": "Ann", "text": "AE"}],
        "jobs": [{"grade": "A", "title": "Account Executive"}]}


def test_no_api_key_returns_message(monkeypatch):
    """With no API key, returns an explanatory message without calling the model."""
    monkeypatch.setattr(sc_mod.config, "OPENAI_API_KEY", "")
    out = send_segment_message("s1", "Why grouped?", _SEG)
    assert "OpenAI API key" in out["text"]


def test_happy_path_and_session_continuity(monkeypatch):
    """Returns the reply and threads previous_response_id on the next turn."""
    clear_segment_session("s1")
    client = _patch(monkeypatch, text="They share enterprise SaaS experience.")
    out = send_segment_message("s1", "Why grouped?", _SEG)
    assert out == {"text": "They share enterprise SaaS experience."}
    send_segment_message("s1", "And their gaps?", _SEG)
    assert client.responses.calls[1]["previous_response_id"] == "resp_1"
    # the segment persona made it into the system prompt
    assert "10y SaaS sales" in client.responses.calls[0]["instructions"]


def test_error_is_caught(monkeypatch):
    """A model error degrades to a friendly message instead of raising."""
    _patch(monkeypatch, exc=RuntimeError("boom"))
    out = send_segment_message("s2", "hi", _SEG)
    assert "something went wrong" in out["text"]
