"""
Offline unit tests for the Structured-Outputs session advisor chats (2.4).

No network: patch the module's `get_client` so `responses.parse` returns a canned
`AdvisorReply`, or raises. Asserts both chats return the reply string, that the saved items /
snapshot + history are forwarded as instructions + input messages, and that no API key / a
model error raises (the blueprint turns those into responses).
"""
import pytest

import jobs_intelligence_ai.services.reporting.session_chat as sc_mod
from jobs_intelligence_ai.services.reporting import analytics_chat, radar_chat
from jobs_intelligence_ai.services.reporting.config import AdvisorReply


class _FakeResponses:
    """`.parse()` records its kwargs and returns a canned AdvisorReply (or raises)."""
    def __init__(self, parsed=None, exc=None):
        self._parsed, self._exc, self.calls = parsed, exc, []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self._exc:
            raise self._exc
        return type("Resp", (), {"output_parsed": self._parsed})()


def _patch(monkeypatch, parsed=None, exc=None):
    responses = _FakeResponses(parsed, exc)
    client = type("C", (), {"responses": responses})()
    monkeypatch.setattr(sc_mod, "get_client", lambda *a, **k: client)
    monkeypatch.setattr(sc_mod.config, "OPENAI_API_KEY", "test-key")
    return responses


def test_analytics_chat_returns_answer(monkeypatch):
    """The parsed AdvisorReply.answer is returned; saved items land in the instructions."""
    resp = _patch(monkeypatch, AdvisorReply(answer="Lead with the IT surge."))
    out = analytics_chat(
        history=[{"role": "user", "content": "What should I lead with?"}],
        items=[{"type": "opportunity", "label": "IT surge", "content": "IT roles up 20%."}],
    )
    assert out == "Lead with the IT surge."
    call = resp.calls[0]
    assert "IT surge" in call["instructions"]              # item grounded into the system prompt
    assert call["input"][-1]["content"] == "What should I lead with?"
    assert call["text_format"] is AdvisorReply


def test_radar_chat_appends_user_message(monkeypatch):
    """radar_chat appends the latest message and grounds the snapshot in the instructions."""
    resp = _patch(monkeypatch, AdvisorReply(answer="Focus on nursing in Wien."))
    out = radar_chat(
        message="Where should I focus?",
        history=[{"role": "assistant", "content": "Earlier reply."}],
        context={"totals": {"total_active": 1000, "stale_30": 200}, "headline": "Tight market"},
    )
    assert out == "Focus on nursing in Wien."
    call = resp.calls[0]
    assert "MARKET SNAPSHOT" in call["instructions"] and "Tight market" in call["instructions"]
    assert call["input"][-1] == {"role": "user", "content": "Where should I focus?"}


def test_no_key_raises(monkeypatch):
    """Without an API key both chats raise (no model call)."""
    monkeypatch.setattr(sc_mod.config, "OPENAI_API_KEY", "")
    with pytest.raises(RuntimeError):
        analytics_chat([{"role": "user", "content": "hi"}], [])
    with pytest.raises(RuntimeError):
        radar_chat("hi", [], {})


def test_model_error_propagates(monkeypatch):
    """A model error propagates so the blueprint can report it."""
    _patch(monkeypatch, exc=RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        analytics_chat([{"role": "user", "content": "hi"}], [])


def test_none_parsed_raises(monkeypatch):
    """A null output_parsed raises rather than returning a bad shape."""
    _patch(monkeypatch, parsed=None)
    with pytest.raises(ValueError):
        radar_chat("hi", [], {})
