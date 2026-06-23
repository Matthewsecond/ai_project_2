"""
Offline unit tests for the Structured-Outputs Highlighter (2.3 #2c).

No network: patch the module's `get_client` so `responses.parse` returns a canned
`HighlightResult`, then assert the returned indices map to job_ids and that bad indices
/ failures degrade to nothing highlighted.
"""
import jobs_intelligence_ai.services.enrichment.highlighter as highlighter_mod
from jobs_intelligence_ai.services.enrichment.highlighter import Highlighter
from jobs_intelligence_ai.services.enrichment.config import HighlightResult


class _FakeResponses:
    """`.parse()` returns a canned HighlightResult (mimicking output_parsed), or raises."""
    def __init__(self, parsed=None, exc=None):
        self._parsed, self._exc = parsed, exc

    def parse(self, **kwargs):
        if self._exc:
            raise self._exc
        return type("Resp", (), {"output_parsed": self._parsed})()


def _patch_client(monkeypatch, parsed=None, exc=None):
    client = type("C", (), {"responses": _FakeResponses(parsed, exc)})()
    monkeypatch.setattr(highlighter_mod, "get_client", lambda *a, **k: client)


def _jobs():
    return [{"job_id": "a"}, {"job_id": "b"}, {"job_id": "c"}]


def test_indices_map_to_job_ids(monkeypatch):
    """The model's 0-based indices select the matching jobs' ids, in order."""
    _patch_client(monkeypatch, HighlightResult(indices=[0, 2]))
    assert Highlighter().highlight("remote roles", _jobs()) == ["a", "c"]


def test_out_of_range_indices_are_skipped(monkeypatch):
    """Indices past the end of the list are ignored, not errors."""
    _patch_client(monkeypatch, HighlightResult(indices=[1, 99]))
    assert Highlighter().highlight("remote roles", _jobs()) == ["b"]


def test_jobs_without_id_are_skipped(monkeypatch):
    """A matched job lacking a job_id contributes nothing."""
    _patch_client(monkeypatch, HighlightResult(indices=[0, 1]))
    assert Highlighter().highlight("x", [{"job_id": "a"}, {"title": "no id"}]) == ["a"]


def test_empty_indices_returns_empty(monkeypatch):
    """No matches → empty list."""
    _patch_client(monkeypatch, HighlightResult(indices=[]))
    assert Highlighter().highlight("nothing matches", _jobs()) == []


def test_failure_highlights_nothing(monkeypatch):
    """If the API call raises, nothing is highlighted — never fatal."""
    _patch_client(monkeypatch, exc=RuntimeError("boom"))
    assert Highlighter().highlight("remote roles", _jobs()) == []


def test_blank_criterion_or_no_jobs_short_circuits(monkeypatch):
    """No criterion or no jobs → [] with no model call."""
    _patch_client(monkeypatch, exc=AssertionError("should not be called"))
    assert Highlighter().highlight("", _jobs()) == []
    assert Highlighter().highlight("remote", []) == []
