"""
Offline unit tests for the Structured-Outputs opportunity briefing (2.3 #4).

No network: patch the module's `get_client` so `responses.parse` returns a canned schema
object (mimicking `output_parsed`), or raises. Asserts the briefing dict is returned shape-
intact, that suggest_filters drops options not in the provided lists, and that a missing key
or API failure degrades to the static fallback rather than raising.
"""
import jobs_intelligence_ai.services.reporting.opportunity_briefing as ob_mod
from jobs_intelligence_ai.services.reporting.opportunity_briefing import (
    generate_briefing, suggest_filters,
)
from jobs_intelligence_ai.services.reporting.config import (
    BriefingResult, _Opportunity, _UrgencyAlert, FilterSuggestion,
)


class _FakeResponses:
    """`.parse()` returns a canned schema object (as output_parsed), or raises."""
    def __init__(self, parsed=None, exc=None):
        self._parsed, self._exc = parsed, exc

    def parse(self, **kwargs):
        if self._exc:
            raise self._exc
        return type("Resp", (), {"output_parsed": self._parsed})()


def _patch_client(monkeypatch, parsed=None, exc=None):
    client = type("C", (), {"responses": _FakeResponses(parsed, exc)})()
    monkeypatch.setattr(ob_mod, "get_client", lambda *a, **k: client)
    monkeypatch.setattr(ob_mod.config, "OPENAI_API_KEY", "test-key")


_TOTALS = {"total_active": 1000, "stale_30": 200, "urgent_14d": 12}


def test_generate_briefing_returns_parsed_dict(monkeypatch):
    """A successful structured call is returned as a plain dict with all briefing keys."""
    parsed = BriefingResult(
        top_opportunities=[_Opportunity(label="IT · Wien", reason="high volume", signal="strong")],
        underserved=[], urgency_alerts=[_UrgencyAlert(label="Nursing", count=8, note="≤14d")],
        trend_summary="Accelerating.", recommendations=["Source IT in Wien."],
        headline="Hot market for IT")
    _patch_client(monkeypatch, parsed)
    out = generate_briefing([], [], [], [], _TOTALS)
    assert out["headline"] == "Hot market for IT"
    assert out["top_opportunities"][0]["signal"] == "strong"
    assert out["urgency_alerts"][0]["count"] == 8


def test_generate_briefing_falls_back_on_failure(monkeypatch):
    """An API error degrades to the static fallback (headline from totals), never raises."""
    _patch_client(monkeypatch, exc=RuntimeError("boom"))
    out = generate_briefing([], [], [], [], _TOTALS)
    assert "1,000 active jobs" in out["headline"]
    assert out["top_opportunities"] == []


def test_generate_briefing_no_key_uses_fallback(monkeypatch):
    """With no API key, the briefing is the static fallback without calling the model."""
    monkeypatch.setattr(ob_mod.config, "OPENAI_API_KEY", "")
    monkeypatch.setattr(ob_mod, "get_client",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not call")))
    out = generate_briefing([], [], [], [], _TOTALS)
    assert out["trend_summary"].startswith("Trend data unavailable")


def test_suggest_filters_keeps_only_valid_options(monkeypatch):
    """occ_groups / states / portals not present in the provided lists are dropped."""
    parsed = FilterSuggestion(
        occ_groups=["IT", "Bogus sector"], states=["Wien", "Atlantis"],
        portals=["karriere.at"], min_salary=3000,
        explanation="Focus on IT in Vienna.", count_hint="~200 jobs")
    _patch_client(monkeypatch, parsed)
    out = suggest_filters("IT roles in Vienna",
                          sectors=["IT", "Finance"], states=["Wien"], portals=["karriere.at"])
    assert out["occ_groups"] == ["IT"]          # "Bogus sector" filtered out
    assert out["states"] == ["Wien"]            # "Atlantis" filtered out
    assert out["min_salary"] == 3000


def test_suggest_filters_falls_back_on_failure(monkeypatch):
    """A model failure returns the empty-filter fallback carrying the reason."""
    _patch_client(monkeypatch, exc=RuntimeError("nope"))
    out = suggest_filters("anything", ["IT"], ["Wien"], ["karriere.at"])
    assert out["occ_groups"] == []
    assert "AI suggestion unavailable" in out["explanation"]
