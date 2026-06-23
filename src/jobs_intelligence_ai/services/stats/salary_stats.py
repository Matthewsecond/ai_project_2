"""
statistics/salary_stats.py — Salary benchmark queries against the live DB.

Fetches all numeric salaries for a given occupational group (active jobs only)
and computes descriptive statistics in Python so we're not tied to MySQL's
limited percentile support.
"""
import logging
import statistics as _stats
from functools import lru_cache

from sqlalchemy import text
from jobs_intelligence_ai import config

logger = logging.getLogger(__name__)


# ── Cache: group stats rarely change within a session ────────────────────────
# TTL is per-process (cache cleared on restart).  Fine for a demo/session tool.
@lru_cache(maxsize=128)
def get_group_stats(occ_group: str, state: str | None = None) -> dict:
    """
    Return salary statistics for all active jobs in an occupational group.

    Parameters
    ----------
    occ_group : str   e.g. "IT/EDV", "Medizin/Pflege"
    state     : str | None   optional Austrian Bundesland filter

    Returns
    -------
    {
        "occ_group": str,
        "count":     int,   # jobs with a numeric salary
        "mean":      float,
        "median":    float,
        "std":       float,
        "min":       float,
        "max":       float,
        "p25":       float,
        "p75":       float,
        "p90":       float,
    }
    Returns an empty dict (count=0) if no data found.
    """
    from jobs_intelligence_ai.infra.database import get_engine  # lazy import to avoid circular deps

    # No occupational_group column (e.g. SK) → no group-level salary stats.
    if not config.PROFILE.col_present("occ_group"):
        return {"occ_group": occ_group, "count": 0}

    c = config.COL
    params: dict = {"occ_group": occ_group}
    state_clause = ""
    if state:
        state_clause = f"AND `{c['state']}` = :state"
        params["state"] = state

    sql = f"""
        SELECT `{c['salary']}`
        FROM View_Jobs_Full
        WHERE `{c['occ_group']}` = :occ_group
          AND `{c['salary']}` IS NOT NULL
          AND `{c['salary']}` > 0
          {state_clause}
    """

    try:
        with get_engine().connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
    except Exception as exc:
        logger.error("salary_stats query failed: %s", exc)
        return {"occ_group": occ_group, "count": 0}

    salaries = []
    for row in rows:
        try:
            v = float(row[0])
            if v > 0:
                salaries.append(v)
        except (TypeError, ValueError):
            pass

    if not salaries:
        return {"occ_group": occ_group, "count": 0}

    salaries.sort()
    n = len(salaries)

    def _percentile(data: list[float], p: float) -> float:
        """Linear interpolation percentile (same as NumPy default)."""
        idx = (p / 100) * (len(data) - 1)
        lo, hi = int(idx), min(int(idx) + 1, len(data) - 1)
        frac = idx - lo
        return data[lo] + frac * (data[hi] - data[lo])

    return {
        "occ_group": occ_group,
        "state":     state,
        "count":     n,
        "mean":      round(_stats.mean(salaries), 2),
        "median":    round(_stats.median(salaries), 2),
        "std":       round(_stats.pstdev(salaries), 2),
        "min":       round(salaries[0], 2),
        "max":       round(salaries[-1], 2),
        "p25":       round(_percentile(salaries, 25), 2),
        "p75":       round(_percentile(salaries, 75), 2),
        "p90":       round(_percentile(salaries, 90), 2),
    }


def salary_percentile_rank(salary: float, occ_group: str, state: str | None = None) -> float | None:
    """
    Return 0–100 percentile rank of a salary within its occupational group.
    Returns None if no group data is available.
    """
    stats = get_group_stats(occ_group, state)
    if not stats.get("count"):
        return None

    # Re-fetch raw salaries (cached above, cheap second call)
    from jobs_intelligence_ai.infra.database import get_engine
    c = config.COL
    params: dict = {"occ_group": occ_group}
    state_clause = f"AND `{c['state']}` = :state" if state else ""
    if state:
        params["state"] = state

    sql = f"""
        SELECT `{c['salary']}`
        FROM View_Jobs_Full
        WHERE `{c['occ_group']}` = :occ_group
          AND `{c['salary']}` IS NOT NULL
          AND `{c['salary']}` > 0
          {state_clause}
    """
    try:
        with get_engine().connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        salaries = sorted(float(r[0]) for r in rows if r[0])
        below = sum(1 for s in salaries if s < salary)
        return round(below / len(salaries) * 100, 1)
    except Exception:
        return None


def invalidate_cache():
    """Call this if the DB is refreshed within a long-running process."""
    get_group_stats.cache_clear()
