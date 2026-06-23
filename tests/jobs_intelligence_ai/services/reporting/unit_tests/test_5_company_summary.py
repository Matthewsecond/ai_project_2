"""
Offline unit tests for the Structured-Outputs company hiring-profile summary (2.4).

No network: patch the module's `get_client` so `responses.parse` returns a canned
`CompanySummary`, or raises. Asserts the summary string is returned, and that no API key /
null output / a model error all degrade to "" (the summary is an optional flourish, so it
must never raise).
"""
import jobs_intelligence_ai.services.reporting.company_summary as cs_mod
from jobs_intelligence_ai.services.reporting import summarize_company
from jobs_intelligence_ai.services.reporting.config import CompanySummary


class _FakeResponses:
    """`.parse()` returns a canned CompanySummary (as output_parsed), or raises."""
    def __init__(self, parsed=None, exc=None):
        self._parsed, self._exc = parsed, exc

    def parse(self, **kwargs):
        if self._exc:
            raise self._exc
        return type("Resp", (), {"output_parsed": self._parsed})()


def _patch(monkeypatch, parsed=None, exc=None):
    client = type("C", (), {"responses": _FakeResponses(parsed, exc)})()
    monkeypatch.setattr(cs_mod, "get_client", lambda *a, **k: client)
    monkeypatch.setattr(cs_mod.config, "OPENAI_API_KEY", "test-key")


_ARGS = dict(
    company_name="ACME GmbH", total=42,
    top_titles=[{"title": "Backend Engineer", "count": 10}],
    top_occ=[{"group": "IT & Software", "count": 20}],
    sal_stats={"min": 3000, "max": 5000, "mean": 4000},
    states=["Wien"], portals=["karriere.at"], work_types={"Vollzeit": 30},
)


def test_returns_summary(monkeypatch):
    """A canned CompanySummary comes back as the trimmed summary string."""
    _patch(monkeypatch, CompanySummary(summary="  ACME is an IT employer in Vienna.  "))
    assert summarize_company(**_ARGS) == "ACME is an IT employer in Vienna."


def test_no_key_returns_empty(monkeypatch):
    """With no API key the summary is "" and no model call is made."""
    monkeypatch.setattr(cs_mod.config, "OPENAI_API_KEY", "")
    monkeypatch.setattr(cs_mod, "get_client",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not call")))
    assert summarize_company(**_ARGS) == ""


def test_none_parsed_returns_empty(monkeypatch):
    """A null output_parsed degrades to "" rather than raising."""
    _patch(monkeypatch, parsed=None)
    assert summarize_company(**_ARGS) == ""


def test_model_error_returns_empty(monkeypatch):
    """A model error degrades to "" — the company response still renders without a summary."""
    _patch(monkeypatch, exc=RuntimeError("boom"))
    assert summarize_company(**_ARGS) == ""
