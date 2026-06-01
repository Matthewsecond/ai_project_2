"""
database.py — SQLAlchemy connection pool + query helpers.

Fetch functions (fetch_jobs_by_ids, fetch_jobs_for_matching, etc.) still read
from View_Jobs_Full because they need every column (skills, contacts, geo …).

get_filter_options() queries the underlying tables directly — the view embeds
3 correlated subqueries that make even a simple SELECT DISTINCT prohibitively
slow at scale.
"""
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool
import config

# ─── Engine (shared, created once) ───────────────────────────────────────────
_engine = None

def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            config.DATABASE_URL,
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            connect_args={
                "connect_timeout": 10,
                "read_timeout":    30,   # kill query if server takes > 30s to respond
                "write_timeout":   30,
            },
        )
    return _engine


def describe_view():
    """Return raw DESCRIBE output for View_Jobs_Full — used by /debug/schema."""
    with get_engine().connect() as conn:
        result = conn.execute(text("DESCRIBE View_Jobs_Full"))
        return [dict(row._mapping) for row in result]


# ─── Filter helpers ────────────────────────────────────────────────────────────

_DB = "Jobs_Intelligence_Austria"

# Simple in-memory cache: {"data": {...}, "ts": float}
import time as _time
_filter_cache: dict = {}
_FILTER_TTL = 300   # seconds (5 minutes)


def get_filter_options(force: bool = False) -> dict:
    """
    Return distinct values for each filter dropdown.

    Results are cached in memory for 5 minutes so rapid page loads / tab
    switches don't hit the DB repeatedly.

    Queries the underlying tables directly (NOT View_Jobs_Full) so we avoid
    the 3 correlated subqueries embedded in the view.  Only active jobs
    (status IN ('new','updated')) are considered so stale/closed values don't
    pollute the dropdowns.

    occ_groups is capped: we only return groups that have >= 10 active jobs,
    ordered by job count descending, max 300.  The raw distinct count is 8,000+
    which produces a 458 KB JSON blob and thousands of <option> DOM nodes.
    """
    now = _time.monotonic()
    if not force and _filter_cache.get("data") and (now - _filter_cache.get("ts", 0)) < _FILTER_TTL:
        return _filter_cache["data"]

    options: dict = {}

    queries = {
        "states": f"""
            SELECT DISTINCT l.location
            FROM {_DB}.locations l
            INNER JOIN {_DB}.jobs j ON j.location_id = l.id
            WHERE j.status IN ('new','updated')
              AND l.location IS NOT NULL
            ORDER BY l.location
        """,
        # Only groups with >= 10 active jobs, sorted by frequency, max 300.
        # Still 300 useful values; avoids sending 8 000-row payloads.
        "occ_groups": f"""
            SELECT j.occupational_group
            FROM {_DB}.jobs j
            WHERE j.status IN ('new','updated')
              AND j.occupational_group IS NOT NULL
              AND j.occupational_group != 'keine Zuordnung'
            GROUP BY j.occupational_group
            HAVING COUNT(*) >= 10
            ORDER BY COUNT(*) DESC
            LIMIT 300
        """,
        "portals": f"""
            SELECT DISTINCT j.portal
            FROM {_DB}.jobs j
            WHERE j.status IN ('new','updated')
              AND j.portal IS NOT NULL
            ORDER BY j.portal
        """,
    }

    with get_engine().connect() as conn:
        for key, sql in queries.items():
            try:
                result = conn.execute(text(sql))
                options[key] = [row[0] for row in result if row[0]]
            except Exception as e:
                options[key] = []
                options[f"{key}_error"] = str(e)

    # Pin "ams" to the top of the portals list
    portals = options.get("portals", [])
    if "ams" in portals:
        portals = ["ams"] + [p for p in portals if p != "ams"]
        options["portals"] = portals

    # Cache the result
    _filter_cache["data"] = options
    _filter_cache["ts"]   = now
    return options


# ─── Fetch by IDs (used after vector store search) ────────────────────────────

def fetch_jobs_by_ids(job_ids: list) -> list[dict]:
    """
    Fetch full job records for a list of numeric IDs.
    Returns a list of dicts, one per job found.
    """
    if not job_ids:
        return []

    c = config.COL
    placeholders = ", ".join([f":id_{i}" for i in range(len(job_ids))])
    params = {f"id_{i}": v for i, v in enumerate(job_ids)}

    sql = f"""
        SELECT *
        FROM View_Jobs_Full
        WHERE `{c['job_id']}` IN ({placeholders})
    """

    with get_engine().connect() as conn:
        try:
            result = conn.execute(text(sql), params)
            keys = list(result.keys())
            rows = [dict(zip(keys, row)) for row in result]
        except Exception:
            rows = []

    # Try to add lat/lon if separate columns exist
    _add_geo(rows)
    return rows


# ─── Fetch for matching (hard filters applied) ────────────────────────────────

def fetch_jobs_for_matching(filters: dict, limit: int = 500) -> list[dict]:
    """
    Fetch jobs from View_Jobs_Full applying hard filters.
    Special filter key `_positions` does a LIKE search on the title column.
    """
    c = config.COL

    where_clauses = []
    params = {}

    if filters.get("state"):
        where_clauses.append(f"`{c['state']}` = :state")
        params["state"] = filters["state"]

    if filters.get("occ_group"):
        where_clauses.append(f"`{c['occ_group']}` = :occ_group")
        params["occ_group"] = filters["occ_group"]

    if filters.get("portal"):
        where_clauses.append(f"`{c['portal']}` = :portal")
        params["portal"] = filters["portal"]

    if filters.get("city"):
        where_clauses.append(f"`{c['city']}` LIKE :city")
        params["city"] = f"%{filters['city']}%"

    # Position-name fallback: used when vector store returned titles but no IDs
    if filters.get("_positions"):
        pos_clauses = []
        for i, pos in enumerate(filters["_positions"]):
            key = f"pos_{i}"
            pos_clauses.append(f"`{c['title']}` LIKE :{key}")
            params[key] = f"%{pos[:60]}%"   # trim to avoid too-long LIKE values
        if pos_clauses:
            where_clauses.append(f"({' OR '.join(pos_clauses)})")

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    params["limit"] = limit

    sql = f"""
        SELECT *
        FROM View_Jobs_Full
        {where_sql}
        LIMIT :limit
    """

    rows = []
    with get_engine().connect() as conn:
        try:
            result = conn.execute(text(sql), params)
            keys = list(result.keys())
            rows = [dict(zip(keys, row)) for row in result]
        except Exception as e:
            raise

    _add_geo(rows)
    return rows


# ─── Fetch by title + company (fallback when AI IDs are stale) ───────────────

def fetch_jobs_by_title_company(candidates: list[dict]) -> list[dict]:
    """
    For each {title, company} pair, find the best matching DB row using LIKE.
    Returns rows that matched; each row gets an extra '_matched_title' key with
    the original title used for lookup so the caller can map it back.
    """
    if not candidates:
        return []

    c = config.COL
    rows_out = []

    import re as _re

    def _title_fragment(t: str) -> str:
        """Extract a short, searchable fragment from a job title."""
        # Split on common separators and take the first meaningful part
        fragment = _re.split(r'[/(,]', t)[0].strip()
        # Remove trailing punctuation and gender markers like *in, (m/w/d), etc.
        fragment = _re.sub(r'[\*\(].*$', '', fragment).strip()
        return fragment[:50] if fragment else t[:50]

    with get_engine().connect() as conn:
        for cand in candidates:
            title   = (cand.get("title") or "")[:80].strip()
            company = (cand.get("company") or "")[:80].strip()
            if not title:
                continue

            fragment = _title_fragment(title)
            params: dict = {"title": f"%{fragment}%"}
            company_clause = ""
            if company:
                company_clause = f" AND `{c['company']}` LIKE :company"
                params["company"] = f"%{company}%"

            sql = f"""
                SELECT *
                FROM View_Jobs_Full
                WHERE `{c['title']}` LIKE :title
                {company_clause}
                ORDER BY `{c['job_id']}` DESC
                LIMIT 1
            """
            try:
                result = conn.execute(text(sql), params)
                keys   = list(result.keys())
                found  = [dict(zip(keys, row)) for row in result]
                if not found and company:
                    # retry without company constraint
                    sql2 = f"""
                        SELECT *
                        FROM View_Jobs_Full
                        WHERE `{c['title']}` LIKE :title
                        ORDER BY `{c['job_id']}` DESC
                        LIMIT 1
                    """
                    result2 = conn.execute(text(sql2), {"title": f"%{fragment}%"})
                    keys    = list(result2.keys())
                    found   = [dict(zip(keys, row)) for row in result2]
                if found:
                    found[0]["_matched_title"] = title
                    rows_out.append(found[0])
            except Exception:
                continue

    _add_geo(rows_out)
    return rows_out


# ─── Geo helper ───────────────────────────────────────────────────────────────

def _add_geo(rows: list[dict]):
    """
    Try to pull _lat/_lon from the row itself (if the view includes lat/lon columns).
    Falls back to None silently if the columns don't exist.
    """
    c = config.COL
    lat_col = c.get("lat", "latitude")
    lon_col = c.get("lon", "longitude")

    for r in rows:
        r["_lat"] = r.get(lat_col)
        r["_lon"] = r.get(lon_col)
