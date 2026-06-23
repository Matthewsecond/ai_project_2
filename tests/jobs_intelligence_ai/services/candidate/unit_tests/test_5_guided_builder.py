"""
Offline unit tests for the Structured-Outputs guided-builder calls (2.4).

No network: patch the module's `get_client` so `responses.parse` returns a canned schema
object, or raises. Asserts field extraction drops empty fields and grounds the catalog/draft
in the prompt, that the reply is returned as a dict (with options as {value,label} dicts),
and that no-key / error behaviour differs by call (extract returns {}/raises; reply always
degrades to {} so the chat keeps working).
"""
import jobs_intelligence_ai.services.candidate.guided_builder as gb_mod
from jobs_intelligence_ai.services.candidate import extract_guided_fields, phrase_guided_reply
from jobs_intelligence_ai.services.candidate.config import (
    GuidedFieldUpdates, GuidedReply, GuidedRegionOption,
)

import pytest


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
    monkeypatch.setattr(gb_mod, "get_client", lambda *a, **k: client)
    monkeypatch.setattr(gb_mod.config, "OPENAI_API_KEY", "test-key")
    return responses


_KW = dict(draft="{}", locked="[]", catalog="it — IT & software",
           last_field="", offer="none", salary="none")


def test_extract_drops_empty_fields(monkeypatch):
    """Only the mentioned (non-empty) fields survive; the catalog grounds the prompt."""
    parsed = GuidedFieldUpdates(sector=["it"], roles=["Java Developer"])
    resp = _patch(monkeypatch, parsed)
    out = extract_guided_fields("We need a Java developer.", **_KW)
    assert out == {"sector": ["it"], "roles": ["Java Developer"]}   # empty lists / null scalars dropped
    assert "IT & software" in resp.calls[0]["instructions"]


def test_extract_no_key_returns_empty(monkeypatch):
    """With no API key, extraction returns {} without calling the model."""
    monkeypatch.setattr(gb_mod.config, "OPENAI_API_KEY", "")
    monkeypatch.setattr(gb_mod, "get_client",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not call")))
    assert extract_guided_fields("note", **_KW) == {}


def test_extract_model_error_raises(monkeypatch):
    """A model error in extraction propagates so the blueprint can return a 500."""
    _patch(monkeypatch, exc=RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        extract_guided_fields("note", **_KW)


_REPLY_KW = dict(lang="English", last_question="", field_updates="{}",
                 user_edits="none", draft="{}", facets="none yet", salary_hint="none available")


def test_reply_returns_dict_with_options(monkeypatch):
    """The reply comes back as a dict; region options serialise to {value,label} dicts."""
    parsed = GuidedReply(
        reply="Great — IT it is.", next_question="Which region?", facet="states",
        answer_field="states", suggestions=[],
        options=[GuidedRegionOption(value="Wien", label="Vienna")])
    _patch(monkeypatch, parsed)
    out = phrase_guided_reply("IT", **_REPLY_KW)
    assert out["reply"] == "Great — IT it is."
    assert out["facet"] == "states"
    assert out["options"] == [{"value": "Wien", "label": "Vienna"}]


def test_reply_degrades_to_empty(monkeypatch):
    """No key, a model error, or a null parse all degrade to {} (the bp applies defaults)."""
    monkeypatch.setattr(gb_mod.config, "OPENAI_API_KEY", "")
    assert phrase_guided_reply("IT", **_REPLY_KW) == {}
    _patch(monkeypatch, exc=RuntimeError("boom"))
    assert phrase_guided_reply("IT", **_REPLY_KW) == {}
    _patch(monkeypatch, parsed=None)
    assert phrase_guided_reply("IT", **_REPLY_KW) == {}
