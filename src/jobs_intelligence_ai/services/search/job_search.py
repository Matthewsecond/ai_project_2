"""
job_search.py — Fetch the converged ids' rows from MySQL (between the stages).

JobSearch talks to MySQL ONLY. Given the converged set of ids, it fetches the
rows in a single query, applies the hard filters (state, city, …), and serializes
them into candidate job dicts — UNGRADED. The Grader assigns scores/grades next.
"""
import logging

from jobs_intelligence_ai.infra.database import fetch_jobs_by_ids
from jobs_intelligence_ai import config

from . import utils
from .exceptions import JobSearchError

logger = logging.getLogger(__name__)


class JobSearch:
    """Turns the converged id set into filtered, serialized (ungraded) job dicts."""

    def fetch(self, ids: list, filters: dict) -> list[dict]:
        """Fetch rows for the ids (one query), hard-filter, and serialize."""
        rows = self.search_by_id(ids)
        return [utils.serialize_job(row)
                for row in rows.values()
                if utils.passes_filters(row, filters)]

    def search_by_id(self, ids: list) -> dict[str, dict]:
        """job_id (str) → DB row, fetched in one query."""
        ids = [i for i in ids if i]
        if not ids:
            return {}
        try:
            rows = fetch_jobs_by_ids(ids)
        except Exception as e:
            raise JobSearchError(f"resolving ids to DB rows failed: {e}") from e
        return {str(r.get(config.COL["job_id"])): r for r in rows}
