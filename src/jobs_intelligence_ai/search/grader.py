"""
grader.py — Score the converged job set against the candidate (Stage 2).

Grader talks to OpenAI ONLY. Given the candidate profile and the fixed set of
candidate jobs, it scores each one in a SINGLE batched, rubric-anchored call —
the authoritative, reproducible grade. There's no max-over-passes inflation: one
consistent judgment over a fixed set, so the same set grades the same way.

Each job dict is updated in place with score / score_pct / grade / match_reason.
If the call fails or returns short, the affected jobs fall back to a neutral
score rather than crashing the search.
"""
import logging

from pydantic import BaseModel

from . import utils

logger = logging.getLogger(__name__)


class _Score(BaseModel):
    """One job's grade — the model is constrained to this shape via Structured Outputs."""
    score: float
    match_reason: str


class _Scores(BaseModel):
    """The grader's reply: one _Score per job, in the same order as the input list."""
    scores: list[_Score]


class Grader:
    """Scores a fixed set of jobs against a candidate profile in one model call."""

    def __init__(self, client, config):
        self._client = client
        self._cfg = config

    def grade(self, candidate_text: str, jobs: list[dict]) -> list[dict]:
        if not jobs:
            return []
        cfg = self._cfg

        lines = []
        for i, j in enumerate(jobs):
            skills = (j.get("skills_en") or j.get("skills") or "")[:160]
            blurb  = (j.get("summary") or j.get("description") or "")[:300]
            loc    = ", ".join(filter(None, [j.get("city"), j.get("state")]))
            lines.append(f'{i}. title: {j.get("title","")} | company: {j.get("company","")} '
                         f'| location: {loc} | skills: {skills} | {blurb}')
        prompt = ("CANDIDATE PROFILE:\n" + (candidate_text or "")[:2500] +
                  "\n\nJOBS:\n" + "\n".join(lines))

        # Structured Outputs: the reply is constrained to _Scores and parsed + validated
        # by the SDK, so there is no JSON text to clean up. output_parsed is a _Scores
        # (or None if the model refused / parse failed) → fall back to neutral scores.
        try:
            response = self._client.responses.parse(
                model=cfg.model,
                instructions=cfg.prompt_template.format(label=cfg.country_label),
                input=prompt,
                text_format=_Scores,
            )
            scores = response.output_parsed.scores if response.output_parsed else []
        except Exception as e:
            logger.warning("grading failed (%s) — assigning neutral scores", e)
            scores = []

        return self._apply(jobs, scores)

    def _apply(self, jobs: list[dict], scores: list) -> list[dict]:
        cfg = self._cfg
        for i, job in enumerate(jobs):
            item = scores[i] if i < len(scores) else None
            try:
                score = round(max(0.0, min(1.0, float(item.score))), 3) if item else 0.5
            except Exception:
                score = 0.5
            job["score"]        = score
            job["score_pct"]    = f"{int(score * 100)}%"
            job["grade"]        = utils.grade(score, cfg.score_a_min, cfg.score_b_min)
            job["match_reason"] = (item.match_reason if item else "").strip()
        return jobs
