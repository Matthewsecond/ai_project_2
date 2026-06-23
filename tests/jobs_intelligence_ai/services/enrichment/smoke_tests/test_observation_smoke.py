"""
Live smoke test for the Structured-Outputs HR-observation calls (2.4).

Hits the real API and ASSERTS: an observation about a new language is extracted into the
`languages` override, and the reply phrasing returns a non-empty acknowledgement.

    pytest tests/jobs_intelligence_ai/services/enrichment/smoke_tests -m smoke -s
"""
import os

os.environ.setdefault("COUNTRY", "sk")

import pytest

from jobs_intelligence_ai import config
from jobs_intelligence_ai.services.enrichment import (
    extract_profile_overrides, phrase_observation_reply,
)

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(not config.OPENAI_API_KEY, reason="live observation smoke — needs OPENAI_API_KEY"),
]

_PROFILE = {"name": "Anna Bauer", "title": "Warehouse Supervisor",
            "skills": ["SAP WM", "Forklift"], "languages": "German (native)"}


def test_extract_overrides_live():
    """Live: an observation about a new language yields a `languages` override."""
    out = extract_profile_overrides(_PROFILE, "She mentioned she now speaks fluent English (C1).")
    assert isinstance(out, dict)
    assert out.get("languages")              # the mentioned field was captured


def test_phrase_reply_live():
    """Live: reply phrasing returns a non-empty acknowledgement string."""
    out = phrase_observation_reply(
        "She now speaks fluent English.", {"languages": "German (native), English C1"},
        "Pipeline potential: 12 → 18 roles (+6)")
    assert isinstance(out, str) and out.strip()
