"""
Behavior of `parse_json` (services/search/utils) — the last surviving hand-rolled JSON
extractor. Lives in search/unit_tests because parse_json stayed in search/utils (no
shared/json.py — superseded by Structured Outputs). Relocated here from shared/unit_tests
in the 2.5 follow-up.

The other two extractors this file used to pin are gone, each replaced by Structured
Outputs as its module was repackaged: `chat._parse` (job-search chat, DELETED in 2.3 #5)
and `chat._parse_candidate` (candidate assistant → candidate/assistant.py, 2.3 #7).
`parse_json`'s only live caller now is the legacy `embedding_search` A/B path, so it
stays until that path retires.
"""
from jobs_intelligence_ai.services.search.utils import parse_json

from tests._fixtures import samples


# ── parse_json: array shape (retrieval ids / lists) ─────────────────────────────
def test_parse_json_fenced_array():
    assert parse_json(samples.LLM_ARRAY_FENCED) == [12345, 67890]


def test_parse_json_bare_array():
    assert parse_json(samples.LLM_ARRAY_BARE) == [12345, 67890]


def test_parse_json_array_embedded_in_prose():
    assert parse_json(samples.LLM_ARRAY_WITH_PROSE) == [12345, 67890]


def test_parse_json_empty_returns_empty_list():
    assert parse_json("") == []
    assert parse_json("no json here") == []


def test_parse_json_strips_citation_markers():
    out = parse_json(samples.LLM_ARRAY_WITH_CITATIONS)
    assert out == [{"title": "Engineer"}]
