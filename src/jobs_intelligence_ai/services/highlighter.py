"""
highlighter.py — Flag which jobs in a set satisfy a natural-language criterion.

Powers the assistant's "highlight offers" action (e.g. "roles with travel
benefits"). Given a list of jobs already on screen and a criterion, one model
call decides which jobs qualify and returns their job_ids. Like Rescorer, this
operates on a result set you already have — it is not search.
"""
import logging
from dataclasses import dataclass

from openai import OpenAI

from jobs_intelligence_ai import config
from jobs_intelligence_ai.search.utils import parse_json

logger = logging.getLogger(__name__)


HIGHLIGHT_PROMPT = """You screen job postings for a recruiter. You are given a CRITERION \
and a numbered list of jobs. Decide which jobs satisfy the criterion, judging from each job's \
title, company, salary, skills and description.

Be inclusive when the text clearly states or strongly implies the criterion, but do not invent \
facts that aren't supported by the job text.

Respond with ONLY a JSON array of the 0-based indices of the matching jobs, e.g. [0,3,4]. \
If none match, return []."""


@dataclass
class HighlighterConfig:
    model:           str = config.CHAT_MODEL
    prompt_template: str = HIGHLIGHT_PROMPT
    api_key:         str = config.OPENAI_API_KEY


class Highlighter:
    """Classifies which of the given jobs satisfy a criterion (one model call)."""

    def __init__(self, config: HighlighterConfig | None = None):
        self._cfg = config or HighlighterConfig()
        self._client: OpenAI | None = None

    def _ensure_ready(self) -> None:
        if self._client is None:
            if not self._cfg.api_key or self._cfg.api_key == "your_key_here":
                raise RuntimeError("OpenAI API key not configured — highlight unavailable")
            self._client = OpenAI(api_key=self._cfg.api_key)

    def highlight(self, criterion: str, jobs: list[dict]) -> list:
        """Return the job_ids of jobs that match the criterion."""
        criterion = (criterion or "").strip()
        if not jobs or not criterion:
            return []
        self._ensure_ready()

        lines = []
        for i, j in enumerate(jobs):
            skills = (j.get("skills_en") or j.get("skills") or "")[:200]
            blurb  = (j.get("description") or j.get("summary") or "")[:700]
            loc    = ", ".join(filter(None, [j.get("city"), j.get("state")]))
            lines.append(f'{i}. title: {j.get("title","")} | company: {j.get("company","")} '
                         f'| location: {loc} | salary: {j.get("salary","")} | skills: {skills} | {blurb}')
        prompt = f"CRITERION: {criterion}\n\nJOBS:\n" + "\n".join(lines)

        try:
            response = self._client.responses.create(
                model=self._cfg.model,
                instructions=self._cfg.prompt_template,
                input=prompt,
            )
            idxs = parse_json(response.output_text or "")
        except Exception as e:
            logger.warning("highlight failed (%s) — nothing highlighted", e)
            return []

        out = []
        for idx in (idxs if isinstance(idxs, list) else []):
            try:
                j = jobs[int(idx)]
            except (ValueError, TypeError, IndexError):
                continue
            if j.get("job_id") is not None:
                out.append(j["job_id"])
        return out
