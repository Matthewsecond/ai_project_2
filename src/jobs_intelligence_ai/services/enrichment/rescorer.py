"""
rescorer.py — Re-grade a FIXED job set against an (updated) candidate profile.

Powers the "freeze results" workflow: the recruiter locks a set of jobs, then
keeps editing the candidate profile, and Rescorer recomputes each job's fit score
+ reason in one model call WITHOUT changing the set — so they watch the ranking
reshuffle as they add CV details. This is not search (it never adds or drops
jobs); it operates on a list of jobs you already have.
"""
import logging
from dataclasses import dataclass

from jobs_intelligence_ai import config
from jobs_intelligence_ai.shared.llm import get_client
from jobs_intelligence_ai.shared.grading import grade
from .config import RESCORE_PROMPT, RescoreResults

logger = logging.getLogger(__name__)


@dataclass
class RescorerConfig:
    model:         str   = config.CHAT_MODEL
    country_label: str   = config.COUNTRY_LABEL
    score_a_min:   float = config.SCORE_A_MIN
    score_b_min:   float = config.SCORE_B_MIN
    prompt_template: str = RESCORE_PROMPT


class Rescorer:
    """Re-scores a frozen job set against an edited profile via one model call."""

    def __init__(self, config: RescorerConfig | None = None):
        self._cfg = config or RescorerConfig()

    def rescore(self, candidate_text: str, jobs: list[dict]) -> list[dict]:
        """Return [{job_id, score, score_pct, grade, match_reason}] aligned to `jobs`.

        Uses Structured Outputs (responses.parse → validated RescoreResults). On any
        failure / empty reply the current scores are kept (best-effort, never fatal)."""
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
            response = get_client().responses.parse(
                model=cfg.model,
                instructions=cfg.prompt_template.format(label=cfg.country_label),
                input=prompt,
                text_format=RescoreResults,
            )
            scores = response.output_parsed.scores if response.output_parsed else []
        except Exception as e:
            logger.warning("rescore failed (%s) — keeping current scores", e)
            return self._unchanged(jobs)

        if not scores:
            return self._unchanged(jobs)

        out = []
        for j, item in zip(jobs, scores):
            try:
                score = round(max(0.0, min(1.0, float(item.score))), 3)
            except Exception:
                score = 0.5
            out.append(self._row(j.get("job_id"), score,
                                  (item.match_reason or j.get("match_reason") or "").strip()))
        # If the model returned fewer items than jobs, keep the rest unchanged.
        for j in jobs[len(out):]:
            out.append(self._row(j.get("job_id"), float(j.get("score") or 0.5),
                                 j.get("match_reason", "")))
        return out

    def _unchanged(self, jobs: list[dict]) -> list[dict]:
        """Graceful fallback: keep each job's current score (no keyword guesswork)."""
        return [self._row(j.get("job_id"), float(j.get("score") or 0.5), j.get("match_reason", ""))
                for j in jobs]

    def _row(self, job_id, score: float, reason: str) -> dict:
        return {
            "job_id":       job_id,
            "score":        score,
            "score_pct":    f"{int(score * 100)}%",
            "grade":        grade(score, self._cfg.score_a_min, self._cfg.score_b_min),
            "match_reason": reason,
        }
