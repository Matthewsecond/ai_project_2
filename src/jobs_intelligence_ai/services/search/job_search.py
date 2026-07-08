"""
job_search.py — Fetch the converged ids' rows from MySQL (between the stages).

JobSearch talks to MySQL ONLY. Given the converged set of ids, it fetches the
rows in a single query, applies the hard filters (state, city, …), and serializes
them into candidate job dicts — UNGRADED. The Grader assigns scores/grades next.
"""
import logging

from jobs_intelligence_ai.infra.database import fetch_jobs_by_ids, fetch_jobs_for_matching
from jobs_intelligence_ai import config

from . import utils
from .exceptions import JobSearchError

logger = logging.getLogger(__name__)

# Filters fetch_jobs_for_matching can't express as a base-table SQL WHERE (state/
# city/zipcode/company aren't columns on the base table at all; salary/skills/
# job_description/nace/online_since/exclude_staffing need row-level parsing) —
# only passes_filters catches these. When any is set, the SQL pass can't narrow
# the candidate pool at all for that filter, so fetch_by_filters widens the
# window it pulls before the Python pass, or a real match could simply not be
# in a small "most recent overall" sample.
_PYTHON_ONLY_FILTER_KEYS = {
    "state", "city", "postcode", "company", "nace1", "nace2", "nace3",
    "salary_min", "salary_max", "skills", "job_description",
    "online_since", "scraping_date", "available_from", "exclude_staffing",
}


class JobSearch:
    """Turns the converged id set into filtered, serialized (ungraded) job dicts."""

    def fetch(self, ids: list, filters: dict) -> list[dict]:
        """Fetch rows for the ids (one query), hard-filter, and serialize."""
        rows = self.search_by_id(ids)
        return [utils.serialize_job(row)
                for row in rows.values()
                if utils.passes_filters(row, filters)]

    def fetch_by_filters(self, filters: dict, limit: int) -> list[dict]:
        """Plain filter-based browse — no candidate/AI matching involved.

        fetch_jobs_for_matching does the cheap SQL-level narrowing on the base
        table (status, portal, work_time, employment_relationship, education,
        occ_group), newest first. passes_filters is then re-run over that set to
        also catch everything else (see _PYTHON_ONLY_FILTER_KEYS) — the same
        single source of truth the AI-matching path uses, so "filters" means the
        same thing in both modes. Fetches a wider window than `limit` so that
        second pass still has enough rows to work with, then trims to `limit`,
        still newest first.
        """
        needs_wide_window = any(filters.get(k) for k in _PYTHON_ONLY_FILTER_KEYS)
        fetch_limit = (min(max(limit * 200, 4000), 8000) if needs_wide_window
                       else min(max(limit * 10, 300), 2000))
        rows = fetch_jobs_for_matching(filters, limit=fetch_limit)
        jobs = [utils.serialize_job(row) for row in rows if utils.passes_filters(row, filters)]
        jobs.sort(key=lambda j: j.get("created_at") or "", reverse=True)
        return jobs[:limit]

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
