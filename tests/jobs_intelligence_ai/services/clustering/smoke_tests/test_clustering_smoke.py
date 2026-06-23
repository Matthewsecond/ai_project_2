"""
Live smoke tests for the clustering service (2.3 #6).

Hits the real API and ASSERTS: embeddings + Ward clustering split two obviously different
candidate pools into segments; the Structured-Outputs persona synthesis returns a non-empty
{title, summary, persona_text}; and segment chat replies.

    pytest tests/jobs_intelligence_ai/services/clustering/smoke_tests -m smoke -s
"""
import os

os.environ.setdefault("COUNTRY", "sk")

import pytest

from jobs_intelligence_ai import config
from jobs_intelligence_ai.services.clustering import (
    embed_profiles, cluster_labels, synthesize_persona, send_segment_message,
)

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(not config.OPENAI_API_KEY, reason="live clustering smoke — needs OPENAI_API_KEY"),
]

_SALES = "Enterprise SaaS account executive, 9 years closing six-figure B2B deals, Salesforce."
_NURSE = "Registered nurse, 8 years ICU and emergency care, BLS/ACLS certified."


def test_embed_and_cluster_splits_two_professions():
    """Live: two sales + two nursing CVs embed and cluster into 2 segments."""
    texts = [_SALES, _SALES + " SDR to AE.", _NURSE, _NURSE + " Night shifts."]
    vecs = embed_profiles(texts)
    assert vecs.shape[0] == 4
    labels = cluster_labels(vecs, granularity=0.5)
    assert labels[0] == labels[1]            # the two sellers together
    assert labels[2] == labels[3]            # the two nurses together
    assert labels[0] != labels[2]            # sellers ≠ nurses


def test_synthesize_persona_live():
    """Live: the structured persona call returns non-empty title + persona_text."""
    out = synthesize_persona([_SALES, _SALES + " Led a 4-person team."])
    assert out["title"].strip()
    assert len(out["persona_text"].strip()) > 20


def test_segment_chat_live():
    """Live: segment chat returns a non-empty reply about the segment."""
    seg = {"title": "Enterprise SaaS sellers", "summary": "Senior B2B AEs",
           "persona_text": _SALES, "members": [{"name": "Ann", "text": _SALES}],
           "jobs": [{"grade": "A", "title": "Account Executive"}]}
    out = send_segment_message("smoke-seg", "Why are these candidates grouped together?", seg)
    assert out["text"].strip()
