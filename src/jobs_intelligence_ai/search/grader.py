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

from . import utils

logger = logging.getLogger(__name__)


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

        try:
            response = self._client.responses.create(
                model=cfg.model,
                instructions=cfg.prompt_template.format(label=cfg.country_label),
                input=prompt,
            )
            scores = utils.parse_json(response.output_text or "")
        except Exception as e:
            logger.warning("grading failed (%s) — assigning neutral scores", e)
            scores = []

        return self._apply(jobs, scores)

    def _apply(self, jobs: list[dict], scores: list) -> list[dict]:
        cfg = self._cfg
        for i, job in enumerate(jobs):
            item = scores[i] if i < len(scores) and isinstance(scores[i], dict) else {}
            try:
                score = round(max(0.0, min(1.0, float(item.get("score", 0.5)))), 3)
            except Exception:
                score = 0.5
            job["score"]        = score
            job["score_pct"]    = f"{int(score * 100)}%"
            job["grade"]        = utils.grade(score, cfg.score_a_min, cfg.score_b_min)
            job["match_reason"] = (item.get("match_reason") or "").strip()
        return jobs
