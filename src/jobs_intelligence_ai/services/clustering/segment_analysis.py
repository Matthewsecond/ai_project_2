"""
clustering/segment_analysis.py — cross-segment + segment↔job analysis (multi-CV mode).

Two LLM calls relocated from the cluster blueprint and converted to Structured Outputs in
rework 2.4:
  - segment_overview(segments)            → prose opportunity overview across all segments
                                            (SegmentOverview, single `text` field).
  - grade_candidates_for_job(job, cands)  → per-candidate fit scores for one job, in input
                                            order (CandidateGrades — replaces the old
                                            "ONLY a JSON array" prompt + parse_json).

Both build their prompt from the structured inputs and call `responses.parse` via the shared
client; either raises on no API key / model error (the blueprint maps that to a 500). The
score→grade-letter shaping stays in the blueprint (presentation + shared grading thresholds).
"""
import logging

from jobs_intelligence_ai import config
from jobs_intelligence_ai.shared.llm import get_client
from .config import (
    OVERVIEW_MODEL, OVERVIEW_PROMPT, SegmentOverview,
    GRADE_MODEL, GRADE_PROMPT, CandidateGrades,
)

logger = logging.getLogger(__name__)


def segment_overview(segments: list[dict]) -> str:
    """Cross-segment opportunity overview (prose). Raises on no API key / model error.

    `segments` is [{title, summary, candidates, ab_jobs, total_jobs, sample_jobs:[{title,grade}]}]."""
    if not config.OPENAI_API_KEY:
        raise RuntimeError("OpenAI API key not configured")

    lines = []
    for s in segments:
        samples = "; ".join(f"{j.get('title', '')} [{j.get('grade', '')}]"
                            for j in (s.get("sample_jobs") or [])[:6])
        lines.append(
            f"- Segment '{s.get('title', '')}': {s.get('candidates', 0)} candidate(s); "
            f"{s.get('ab_jobs', 0)} strong (A/B) roles of {s.get('total_jobs', 0)} matched. "
            f"Sample strong roles: {samples or 'none'}. {s.get('summary', '')}"
        )
    user_input = "TALENT SEGMENTS (candidates we have vs. open roles that matched them):\n" + "\n".join(lines)

    resp = get_client().responses.parse(
        model=OVERVIEW_MODEL,
        instructions=OVERVIEW_PROMPT,
        input=user_input,
        text_format=SegmentOverview,
    )
    if resp.output_parsed is None:
        raise ValueError("Model returned no overview")
    return resp.output_parsed.text


def grade_candidates_for_job(job: dict, candidates: list[dict]) -> list[dict]:
    """Score each candidate against one job (Structured Outputs).

    Returns [{score, reason}] in the SAME ORDER as `candidates`. Raises on no API key / model
    error. The caller clamps the score and derives the grade letter."""
    if not config.OPENAI_API_KEY:
        raise RuntimeError("OpenAI API key not configured")

    job_desc = (f"Title: {job.get('title', '')}\nCompany: {job.get('company', '')}\n"
                f"Skills: {job.get('skills_en') or job.get('skills') or ''}\n"
                f"{(job.get('description') or '')[:900]}")
    lines = [f"{i}. {c.get('name', '')}: {(c.get('text') or '')[:600]}"
             for i, c in enumerate(candidates)]
    user_input = "JOB:\n" + job_desc + "\n\nCANDIDATES:\n" + "\n".join(lines)

    resp = get_client().responses.parse(
        model=GRADE_MODEL,
        instructions=GRADE_PROMPT,
        input=user_input,
        text_format=CandidateGrades,
    )
    if resp.output_parsed is None:
        raise ValueError("Model returned no candidate scores")
    return [g.model_dump() for g in resp.output_parsed.candidates]
