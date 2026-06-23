"""
Offline unit tests for the analytics session report (2.3 #4 — report_generator).

The AI elaboration is converted to Structured Outputs: patch `get_client` so
`responses.parse` returns a canned `ElaborationList`, and assert each elaboration is merged
back onto its source item by index, with graceful fallback on failure / no key. The PDF
builder is pure reportlab, so we exercise it for real and check it emits a PDF.
"""
import jobs_intelligence_ai.services.reporting.report_generator as rg_mod
from jobs_intelligence_ai.services.reporting.report_generator import (
    elaborate_items, generate_pdf,
)
from jobs_intelligence_ai.services.reporting.config import ElaborationList, _Elaboration


class _FakeResponses:
    """`.parse()` returns a canned ElaborationList (as output_parsed), or raises."""
    def __init__(self, parsed=None, exc=None):
        self._parsed, self._exc = parsed, exc

    def parse(self, **kwargs):
        if self._exc:
            raise self._exc
        return type("Resp", (), {"output_parsed": self._parsed})()


def _patch_client(monkeypatch, parsed=None, exc=None):
    client = type("C", (), {"responses": _FakeResponses(parsed, exc)})()
    monkeypatch.setattr(rg_mod, "get_client", lambda *a, **k: client)
    monkeypatch.setattr(rg_mod.config, "OPENAI_API_KEY", "test-key")


_ITEMS = [
    {"type": "opportunity", "label": "IT surge", "content": "IT roles up 20%."},
    {"type": "trend", "label": "Cooling", "content": "Finance roles down."},
]


def test_elaborate_merges_by_index(monkeypatch):
    """Each elaboration is matched to its source item by 1-based index."""
    parsed = ElaborationList(items=[
        _Elaboration(index=1, heading="IT is hot", elaboration="Para 1\n\nPara 2",
                     action_steps=["Hire IT", "Post now"]),
        _Elaboration(index=2, heading="Finance cools", elaboration="Down.", action_steps=[]),
    ])
    _patch_client(monkeypatch, parsed)
    out = elaborate_items(_ITEMS, context={})
    assert out[0]["heading"] == "IT is hot"
    assert out[0]["action_steps"] == ["Hire IT", "Post now"]
    assert out[1]["heading"] == "Finance cools"
    # original fields are preserved
    assert out[0]["type"] == "opportunity"


def test_elaborate_missing_index_uses_item_fallback(monkeypatch):
    """An item the model skipped keeps its label/content as heading/elaboration."""
    parsed = ElaborationList(items=[
        _Elaboration(index=1, heading="IT is hot", elaboration="x", action_steps=[])])
    _patch_client(monkeypatch, parsed)
    out = elaborate_items(_ITEMS, context={})
    assert out[1]["heading"] == "Cooling"          # fell back to item label
    assert out[1]["action_steps"] == []


def test_elaborate_failure_falls_back(monkeypatch):
    """A model failure returns each item with plain heading/elaboration, no crash."""
    _patch_client(monkeypatch, exc=RuntimeError("boom"))
    out = elaborate_items(_ITEMS, context={})
    assert [o["heading"] for o in out] == ["IT surge", "Cooling"]


def test_elaborate_no_key_skips_call(monkeypatch):
    """With no API key, elaboration is the plain fallback without calling the model."""
    monkeypatch.setattr(rg_mod.config, "OPENAI_API_KEY", "")
    monkeypatch.setattr(rg_mod, "get_client",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not call")))
    out = elaborate_items(_ITEMS, context={})
    assert out[0]["elaboration"] == "IT roles up 20%."


def test_generate_pdf_emits_a_pdf():
    """The pure reportlab builder returns non-empty PDF bytes."""
    elaborated = [{**_ITEMS[0], "heading": "IT is hot",
                   "elaboration": "Para.", "action_steps": ["Do it"]}]
    pdf = generate_pdf(elaborated, context={"totals": {"total_active": 10}, "headline": "Hi"})
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 1000
