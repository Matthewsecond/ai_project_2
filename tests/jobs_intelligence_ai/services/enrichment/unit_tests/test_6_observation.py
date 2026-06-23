"""
Offline unit tests for the Structured-Outputs HR-observation calls (2.4).

No network: patch the module's `get_client` so `responses.parse` returns a canned schema
object, or raises. Asserts override extraction drops null fields and grounds the profile in
the prompt, that no-key/error behaviour differs by call (extract raises; reply degrades to a
safe fallback), and that reply phrasing returns the model text or the fallback.
"""
import pytest

import jobs_intelligence_ai.services.enrichment.observation as obs_mod
from jobs_intelligence_ai.services.enrichment import (
    extract_profile_overrides, phrase_observation_reply,
)
from jobs_intelligence_ai.services.enrichment.config import (
    ObservationOverrides, ObservationReply,
)


class _FakeResponses:
    """`.parse()` records kwargs and returns a canned schema object (or raises)."""
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
    monkeypatch.setattr(obs_mod, "get_client", lambda *a, **k: client)
    monkeypatch.setattr(obs_mod.config, "OPENAI_API_KEY", "test-key")
    return responses


def test_extract_drops_null_fields(monkeypatch):
    """Only the mentioned (non-null) override fields survive; the profile grounds the prompt."""
    parsed = ObservationOverrides(languages="German (fluent)", skills=["SAP"])
    resp = _patch(monkeypatch, parsed)
    out = extract_profile_overrides({"name": "Anna"}, "She actually speaks fluent German.")
    assert out == {"languages": "German (fluent)", "skills": ["SAP"]}   # salary/location/etc. dropped
    assert "Anna" in resp.calls[0]["instructions"]


def test_extract_no_key_returns_empty(monkeypatch):
    """With no API key, extraction returns {} without calling the model."""
    monkeypatch.setattr(obs_mod.config, "OPENAI_API_KEY", "")
    monkeypatch.setattr(obs_mod, "get_client",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not call")))
    assert extract_profile_overrides({"name": "Anna"}, "note") == {}


def test_extract_model_error_raises(monkeypatch):
    """A model error in extraction propagates so the blueprint can return a 500."""
    _patch(monkeypatch, exc=RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        extract_profile_overrides({}, "note")


def test_reply_returns_model_text(monkeypatch):
    """The phrased reply is the model's text when present."""
    _patch(monkeypatch, ObservationReply(reply="Got it — noted her fluent German."))
    out = phrase_observation_reply("note", {"languages": "German"}, "No significant change.")
    assert out == "Got it — noted her fluent German."


def test_reply_degrades_to_fallback(monkeypatch):
    """No key, a model error, or a blank reply all degrade to the safe fallback string."""
    monkeypatch.setattr(obs_mod.config, "OPENAI_API_KEY", "")
    assert phrase_observation_reply("note", {}, "") == "Profile updated."
    _patch(monkeypatch, exc=RuntimeError("boom"))
    assert phrase_observation_reply("note", {}, "") == "Profile updated."
    _patch(monkeypatch, ObservationReply(reply="   "))
    assert phrase_observation_reply("note", {}, "") == "Profile updated."
