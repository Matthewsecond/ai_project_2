"""
Live smoke test for the Structured-Outputs InterviewHelper (2.3 #3).

Hits the real API and ASSERTS the structured calls work end-to-end on the two seams that
matter: generating gap-based questions for a (job, CV) pair, and scoring a strong answer.
Proves the `responses.parse(text_format=…)` calls return valid, sane `output_parsed`.

    pytest tests/jobs_intelligence_ai/services/interview/smoke_tests -m smoke -s
"""
import os

os.environ.setdefault("COUNTRY", "sk")

import pytest

from jobs_intelligence_ai import config
from jobs_intelligence_ai.services.interview import InterviewHelper

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(not config.OPENAI_API_KEY, reason="live interview smoke — needs OPENAI_API_KEY"),
]

_JOB = {
    "title": "Senior Backend Engineer",
    "company": "ACME",
    "skills_en": "Python, PostgreSQL, distributed systems, AWS",
    "description": "Own backend services at scale. 5+ years required, lead design reviews.",
}
_CV = ("8 years building Python microservices; led a 4-engineer team; scaled a payments "
       "platform to 10k req/s on AWS; owned the on-call rotation and incident reviews.")


def test_generate_questions_live():
    """Live: returns several gap-based questions, each with non-empty text and an int id."""
    out = InterviewHelper().generate_questions(_JOB, _CV, n=4)
    assert out["ok"] is True
    assert len(out["questions"]) >= 2
    for q in out["questions"]:
        assert isinstance(q["id"], int)
        assert q["question"].strip()


def test_analyze_strong_answer_live():
    """Live: a concrete, quantified answer is judged complete and scores in the upper range."""
    answer = ("I scaled our payments API from 1k to 10k req/s by adding read replicas and a "
              "Redis cache, cutting p99 latency from 800ms to 120ms over one quarter.")
    out = InterviewHelper().analyze_answer(
        question="Tell me about a time you improved system performance.",
        answer=answer, job=_JOB, cv_text=_CV, final=True)
    assert out["ok"] is True
    assert out["complete"] is True
    assert isinstance(out["score"], int) and out["score"] >= 50
