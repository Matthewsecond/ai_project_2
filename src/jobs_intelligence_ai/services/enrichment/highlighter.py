"""
highlighter.py — Flag which jobs in a set satisfy a natural-language criterion.

Powers the assistant's "highlight offers" action (e.g. "roles with travel
benefits"). Given a list of jobs already on screen and a criterion, one model
call decides which jobs qualify and returns their job_ids. Like Rescorer, this
operates on a result set you already have — it is not search.
"""
import logging
from dataclasses import dataclass

from jobs_intelligence_ai import config
from jobs_intelligence_ai.shared.llm import get_client
from .config import HIGHLIGHT_PROMPT, HighlightResult

logger = logging.getLogger(__name__)


@dataclass
class HighlighterConfig:
    model:           str = config.CHAT_MODEL
    prompt_template: str = HIGHLIGHT_PROMPT


class Highlighter:
    """Classifies which of the given jobs satisfy a criterion (one model call)."""

    def __init__(self, config: HighlighterConfig | None = None):
        self._cfg = config or HighlighterConfig()

    def highlight(self, criterion: str, jobs: list[dict]) -> list:
        """Return the job_ids of jobs that match the criterion.

        Uses Structured Outputs (responses.parse → validated HighlightResult). On any
        failure / empty reply, nothing is highlighted (best-effort, never fatal)."""
        criterion = (criterion or "").strip()
        if not jobs or not criterion:
            return []

        lines = []
        for i, j in enumerate(jobs):
            skills = (j.get("skills_en") or j.get("skills") or "")[:200]
            blurb  = (j.get("description") or j.get("summary") or "")[:700]
            loc    = ", ".join(filter(None, [j.get("city"), j.get("state")]))
            lines.append(f'{i}. title: {j.get("title","")} | company: {j.get("company","")} '
                         f'| location: {loc} | salary: {j.get("salary","")} | skills: {skills} | {blurb}')
        prompt = f"CRITERION: {criterion}\n\nJOBS:\n" + "\n".join(lines)

        try:
            response = get_client().responses.parse(
                model=self._cfg.model,
                instructions=self._cfg.prompt_template,
                input=prompt,
                text_format=HighlightResult,
            )
            idxs = response.output_parsed.indices if response.output_parsed else []
        except Exception as e:
            logger.warning("highlight failed (%s) — nothing highlighted", e)
            return []

        out = []
        for idx in idxs:
            try:
                j = jobs[int(idx)]
            except (ValueError, TypeError, IndexError):
                continue
            if j.get("job_id") is not None:
                out.append(j["job_id"])
        return out
