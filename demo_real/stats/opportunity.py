"""
stats/opportunity.py — Raw opportunity signal extraction from the DB.

Queries go directly to the underlying tables (jobs + locations + companies)
instead of View_Jobs_Full.  The view contains 3 correlated subqueries for
skills/contacts that materialise per-row — making any aggregation on it very
slow.  The opportunity queries never need skills or contacts, so we skip the
view entirely and use proper indexed columns.

Indexes that must exist on `jobs` (created by migration):
    idx_jobs_status_occ     (status, occupational_group)
    idx_jobs_status_portal  (status, portal)
    idx_jobs_status_created (status, created_at)

All queries use created_at as the staleness signal (reliable: when the crawler
first found the job) rather than publication_date (unreliable: future-dated
or old from re-posts).
"""
import logging
import decimal
import datetime

from sqlalchemy import text
import config

logger = logging.getLogger(__name__)

# ── Table / join constants ─────────────────────────────────────────────────────
_DB   = "Jobs_Intelligence_Austria"
_FROM = f"{_DB}.jobs j LEFT JOIN {_DB}.locations l ON l.id = j.location_id"
_FROM_CO = (
    f"{_DB}.jobs j "
    f"LEFT JOIN {_DB}.locations l ON l.id = j.location_id "
    f"LEFT JOIN {_DB}.companies c ON c.id = j.company_id"
)


def _engine():
    from core.database import get_engine
    return get_engine()


# ── Filter helper ──────────────────────────────────────────────────────────────

def _build_filter_clause(filters: dict | None) -> tuple[str, dict]:
    """
    Returns (extra_where_clause, extra_params).
    Clause always starts with ' AND ...' or is empty string.
    Uses qualified column names (j.col / l.col) for direct-table queries.

    Supports both single-value and multi-value (list) filters:
      occ_group  → single  → j.occupational_group = :val
      occ_groups → list    → j.occupational_group IN (:v0, :v1, ...)
    Same pattern for state/states and portal/portals.
    Multi-value always takes priority over its single-value counterpart.
    """
    if not filters:
        return "", {}

    parts  = []
    params = {}

    # ── State / States ────────────────────────────────────────────────────────
    _states = [s for s in (filters.get("states") or []) if s]
    if _states:
        phs = ", ".join(f":f_state_{i}" for i in range(len(_states)))
        parts.append(f"l.location IN ({phs})")
        for i, s in enumerate(_states):
            params[f"f_state_{i}"] = s
    elif filters.get("state"):
        parts.append("l.location = :f_state")
        params["f_state"] = filters["state"]

    # ── Portal / Portals ──────────────────────────────────────────────────────
    _portals = [p for p in (filters.get("portals") or []) if p]
    if _portals:
        phs = ", ".join(f":f_portal_{i}" for i in range(len(_portals)))
        parts.append(f"j.portal IN ({phs})")
        for i, p in enumerate(_portals):
            params[f"f_portal_{i}"] = p
    elif filters.get("portal"):
        parts.append("j.portal = :f_portal")
        params["f_portal"] = filters["portal"]

    # ── Occupational group / groups ───────────────────────────────────────────
    _groups = [g for g in (filters.get("occ_groups") or []) if g]
    if _groups:
        phs = ", ".join(f":f_occ_{i}" for i in range(len(_groups)))
        parts.append(f"j.occupational_group IN ({phs})")
        for i, g in enumerate(_groups):
            params[f"f_occ_{i}"] = g
    elif filters.get("occ_group"):
        parts.append("j.occupational_group = :f_occ_group")
        params["f_occ_group"] = filters["occ_group"]

    # ── Min salary ────────────────────────────────────────────────────────────
    if filters.get("min_salary"):
        try:
            params["f_min_salary"] = int(filters["min_salary"])
            parts.append("CAST(j.salary AS DECIMAL(10,2)) >= :f_min_salary")
        except (ValueError, TypeError):
            pass

    clause = (" AND " + " AND ".join(parts)) if parts else ""
    return clause, params


# ── Sector snapshot ────────────────────────────────────────────────────────────

def get_sector_snapshot(limit: int = 40, filters: dict | None = None) -> list[dict]:
    """Per occupational group: volume, staleness, urgency, salary."""
    fclause, fparams = _build_filter_clause(filters)
    sql = f"""
        SELECT
            j.occupational_group                                             AS occ_group,
            COUNT(*)                                                         AS total_jobs,
            ROUND(AVG(DATEDIFF(NOW(), j.created_at)), 1)                    AS avg_days_in_system,
            MAX(DATEDIFF(NOW(), j.created_at))                              AS max_days_in_system,
            SUM(CASE WHEN DATEDIFF(NOW(), j.created_at) >= 30 THEN 1 ELSE 0 END) AS stale_30,
            SUM(CASE WHEN DATEDIFF(NOW(), j.created_at) >= 60 THEN 1 ELSE 0 END) AS stale_60,
            SUM(CASE WHEN j.application_deadline IS NOT NULL
                          AND j.application_deadline > NOW()
                          AND j.application_deadline < DATE_ADD(NOW(), INTERVAL 14 DAY)
                     THEN 1 ELSE 0 END)                                      AS urgent_deadline,
            ROUND(AVG(CASE WHEN CAST(j.salary AS DECIMAL(10,2)) > 0
                           THEN CAST(j.salary AS DECIMAL(10,2)) END), 0)     AS avg_salary,
            SUM(CASE WHEN j.salary IS NOT NULL AND j.salary != '' AND j.salary != '0'
                     THEN 1 ELSE 0 END)                                      AS jobs_with_salary
        FROM {_FROM}
        WHERE j.status IN ('new','updated')
          AND j.occupational_group IS NOT NULL
          AND j.occupational_group != 'keine Zuordnung'
          {fclause}
        GROUP BY j.occupational_group
        ORDER BY total_jobs DESC
        LIMIT :limit
    """
    return _run(sql, {"limit": limit, **fparams})


# ── State snapshot ─────────────────────────────────────────────────────────────

def get_state_snapshot(filters: dict | None = None) -> list[dict]:
    """Per Austrian Bundesland: volume, staleness, salary, urgent counts."""
    fclause, fparams = _build_filter_clause(filters)
    sql = f"""
        SELECT
            l.location                                                       AS state,
            COUNT(*)                                                         AS total_jobs,
            ROUND(AVG(DATEDIFF(NOW(), j.created_at)), 1)                    AS avg_days_in_system,
            ROUND(AVG(CASE WHEN CAST(j.salary AS DECIMAL(10,2)) > 0
                           THEN CAST(j.salary AS DECIMAL(10,2)) END), 0)     AS avg_salary,
            SUM(CASE WHEN DATEDIFF(NOW(), j.created_at) >= 30 THEN 1 ELSE 0 END) AS stale_30,
            SUM(CASE WHEN j.application_deadline IS NOT NULL
                          AND j.application_deadline > NOW()
                          AND j.application_deadline < DATE_ADD(NOW(), INTERVAL 14 DAY)
                     THEN 1 ELSE 0 END)                                      AS urgent_deadline
        FROM {_FROM}
        WHERE j.status IN ('new','updated')
          AND l.location IS NOT NULL
          {fclause}
        GROUP BY l.location
        ORDER BY total_jobs DESC
    """
    return _run(sql, fparams)


# ── Portal snapshot ────────────────────────────────────────────────────────────

def get_portal_snapshot(filters: dict | None = None) -> list[dict]:
    """Per portal: volume, avg days stale, avg salary."""
    fclause, fparams = _build_filter_clause(filters)
    sql = f"""
        SELECT
            j.portal                                                         AS portal,
            COUNT(*)                                                         AS total_jobs,
            ROUND(AVG(DATEDIFF(NOW(), j.created_at)), 1)                    AS avg_days_in_system,
            ROUND(AVG(CASE WHEN CAST(j.salary AS DECIMAL(10,2)) > 0
                           THEN CAST(j.salary AS DECIMAL(10,2)) END), 0)     AS avg_salary,
            SUM(CASE WHEN DATEDIFF(NOW(), j.created_at) >= 60 THEN 1 ELSE 0 END) AS stale_60
        FROM {_FROM}
        WHERE j.status IN ('new','updated')
          AND j.portal IS NOT NULL
          {fclause}
        GROUP BY j.portal
        ORDER BY total_jobs DESC
        LIMIT 20
    """
    return _run(sql, fparams)


# ── Volume trend (weekly creation rate) ───────────────────────────────────────

def get_volume_trend(weeks: int = 8, filters: dict | None = None) -> list[dict]:
    """Jobs created per week over the last N weeks."""
    fclause, fparams = _build_filter_clause(filters)
    sql = f"""
        SELECT
            YEARWEEK(j.created_at, 1)   AS year_week,
            MIN(DATE(j.created_at))     AS week_start,
            COUNT(*)                    AS jobs_created
        FROM {_FROM}
        WHERE j.status IN ('new','updated')
          AND j.created_at >= DATE_SUB(NOW(), INTERVAL :weeks WEEK)
          {fclause}
        GROUP BY YEARWEEK(j.created_at, 1)
        ORDER BY year_week ASC
    """
    return _run(sql, {"weeks": weeks, **fparams})


# ── Summary totals (header cards) ─────────────────────────────────────────────

def get_summary_totals(filters: dict | None = None) -> dict:
    """Quick totals for the Radar header cards."""
    fclause, fparams = _build_filter_clause(filters)
    sql = f"""
        SELECT
            COUNT(*)                                                              AS total_active,
            SUM(CASE WHEN DATEDIFF(NOW(), j.created_at) >= 30 THEN 1 ELSE 0 END) AS stale_30,
            SUM(CASE WHEN DATEDIFF(NOW(), j.created_at) >= 60 THEN 1 ELSE 0 END) AS stale_60,
            SUM(CASE WHEN j.application_deadline IS NOT NULL
                          AND j.application_deadline > NOW()
                          AND j.application_deadline < DATE_ADD(NOW(), INTERVAL 14 DAY)
                     THEN 1 ELSE 0 END)                                           AS urgent_14d,
            COUNT(DISTINCT j.occupational_group)                                  AS sector_count,
            COUNT(DISTINCT l.location)                                            AS state_count
        FROM {_FROM}
        WHERE j.status IN ('new','updated')
          {fclause}
    """
    rows = _run(sql, fparams)
    return rows[0] if rows else {}


# ── Stale job sample (for the quick-finder list) ──────────────────────────────

def get_stale_jobs(min_days: int = 45, limit: int = 50,
                   occ_group: str = None, state: str = None,
                   portal: str = None) -> list[dict]:
    """Jobs that have been in the system >= min_days."""
    where  = ["j.status IN ('new','updated')",
               "DATEDIFF(NOW(), j.created_at) >= :min_days"]
    params: dict = {"min_days": min_days, "limit": limit}

    if occ_group:
        where.append("j.occupational_group = :occ_group")
        params["occ_group"] = occ_group
    if state:
        where.append("l.location = :state")
        params["state"] = state
    if portal:
        where.append("j.portal = :portal")
        params["portal"] = portal

    sql = f"""
        SELECT
            j.id                        AS job_id,
            j.position                  AS title,
            c.company_crawler_name      AS company,
            l.location                  AS state,
            l.city                      AS city,
            j.occupational_group        AS occ_group,
            j.portal                    AS portal,
            j.salary                    AS salary,
            j.cleaned_link              AS url,
            j.application_deadline      AS application_deadline,
            DATEDIFF(NOW(), j.created_at) AS days_in_system,
            j.created_at,
            j.updated_at
        FROM {_FROM_CO}
        WHERE {' AND '.join(where)}
        ORDER BY days_in_system DESC
        LIMIT :limit
    """
    return _run(sql, params)


# ── Urgent jobs (deadline within N days) ──────────────────────────────────────

def get_urgent_jobs(deadline_days: int = 14, limit: int = 50) -> list[dict]:
    """Jobs whose application deadline falls within the next N days."""
    sql = f"""
        SELECT
            j.id                        AS job_id,
            j.position                  AS title,
            c.company_crawler_name      AS company,
            l.location                  AS state,
            l.city                      AS city,
            j.occupational_group        AS occ_group,
            j.portal                    AS portal,
            j.salary                    AS salary,
            j.cleaned_link              AS url,
            j.application_deadline      AS application_deadline,
            DATEDIFF(j.application_deadline, NOW()) AS days_until_deadline,
            DATEDIFF(NOW(), j.created_at)           AS days_in_system
        FROM {_FROM_CO}
        WHERE j.status IN ('new','updated')
          AND j.application_deadline IS NOT NULL
          AND j.application_deadline > NOW()
          AND j.application_deadline < DATE_ADD(NOW(), INTERVAL :deadline_days DAY)
        ORDER BY j.application_deadline ASC
        LIMIT :limit
    """
    return _run(sql, {"deadline_days": deadline_days, "limit": limit})


# ── Helper ─────────────────────────────────────────────────────────────────────

def _run(sql: str, params: dict) -> list[dict]:
    try:
        with _engine().connect() as conn:
            result = conn.execute(text(sql), params)
            keys = list(result.keys())
            return [dict(zip(keys, (_native(v) for v in row))) for row in result]
    except Exception as exc:
        logger.error("opportunity query failed: %s", exc)
        return []


def _native(val):
    """Convert MySQL Decimal/date types to plain Python so jsonify works."""
    if isinstance(val, decimal.Decimal):
        f = float(val)
        return int(f) if f == int(f) else round(f, 2)
    if isinstance(val, (datetime.date, datetime.datetime)):
        return val.isoformat()
    return val
