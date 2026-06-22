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
from jobs_intelligence_ai import config

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
    """Return raw DESCRIBE output for the active read view — used by /debug/schema."""
    with get_engine().connect() as conn:
        result = conn.execute(text(f"DESCRIBE {config.PROFILE.read_view}"))
        return [dict(row._mapping) for row in result]


# ─── Filter helpers ────────────────────────────────────────────────────────────

_DB = config.DB_SCHEMA

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

    # Per-country dropdown SQL ({db} = active schema). SK omits occ_groups.
    queries = {key: sql.format(db=_DB) for key, sql in config.PROFILE.filter_queries.items()}

    with get_engine().connect() as conn:
        for key, sql in queries.items():
            try:
                result = conn.execute(text(sql))
                options[key] = [row[0] for row in result if row[0]]
            except Exception as e:
                options[key] = []
                options[f"{key}_error"] = str(e)

    # Keep the dropdown contract stable even when a country lacks a facet.
    for key in ("states", "occ_groups", "portals"):
        options.setdefault(key, [])

    # Pin the primary portal to the top of the list (Austria: "ams").
    pin = config.PROFILE.portal_pin
    if pin and pin in options.get("portals", []):
        options["portals"] = [pin] + [p for p in options["portals"] if p != pin]

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
        FROM {config.PROFILE.read_view}
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


def fetch_jobs_by_url(url: str) -> list[dict]:
    """
    Fetch full job record(s) matching a posting URL, exact and trailing-slash
    tolerant. Returns [] when the url isn't in the active read view (→ a candidate
    for live scraping, which is not implemented yet).

    We match a small set of trivial variants with an equality IN-list rather than a
    leading-wildcard LIKE, which would force a full scan of the heavy read view.
    """
    url = (url or "").strip()
    if not url:
        return []

    c = config.COL
    variants = list({url, url.rstrip("/"), url.rstrip("/") + "/"})
    placeholders = ", ".join(f":u_{i}" for i in range(len(variants)))
    params = {f"u_{i}": v for i, v in enumerate(variants)}

    sql = f"""
        SELECT *
        FROM {config.PROFILE.read_view}
        WHERE `{c['url']}` IN ({placeholders})
        LIMIT 5
    """

    with get_engine().connect() as conn:
        try:
            result = conn.execute(text(sql), params)
            keys = list(result.keys())
            rows = [dict(zip(keys, row)) for row in result]
        except Exception:
            rows = []

    _add_geo(rows)
    return rows


# ─── Fetch for matching (hard filters applied) ────────────────────────────────

def fetch_jobs_for_matching(filters: dict, limit: int = 500) -> list[dict]:
    """
    Fetch jobs from the active read view applying hard filters.

    Special filter key `_positions` (used when the vector store returned job titles
    but no usable ids) is resolved on the base `jobs_table` — a fast indexed scan —
    and enriched by id, instead of a leading-wildcard LIKE against the heavy view
    (correlated subqueries + window fn → 30s read-timeout). The base table shares
    the read view's id-space, so the ids feed straight into fetch_jobs_by_ids().
    """
    c = config.COL

    if filters.get("_positions"):
        ids = _resolve_ids_by_position(filters["_positions"], limit)
        return fetch_jobs_by_ids(ids) if ids else []

    where_clauses = []
    params = {}

    if filters.get("state"):
        where_clauses.append(f"`{c['state']}` = :state")
        params["state"] = filters["state"]

    if filters.get("occ_group") and config.PROFILE.col_present("occ_group"):
        where_clauses.append(f"`{c['occ_group']}` = :occ_group")
        params["occ_group"] = filters["occ_group"]

    if filters.get("portal"):
        where_clauses.append(f"`{c['portal']}` = :portal")
        params["portal"] = filters["portal"]

    if filters.get("city"):
        where_clauses.append(f"`{c['city']}` LIKE :city")
        params["city"] = f"%{filters['city']}%"

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    params["limit"] = limit

    sql = f"""
        SELECT *
        FROM {config.PROFILE.read_view}
        {where_sql}
        LIMIT :limit
    """

    with get_engine().connect() as conn:
        result = conn.execute(text(sql), params)
        keys = list(result.keys())
        rows = [dict(zip(keys, row)) for row in result]

    _add_geo(rows)
    return rows


def _resolve_ids_by_position(positions: list, limit: int) -> list:
    """Resolve job titles → ids via a fast scan of the base jobs table.

    Avoids a leading-wildcard LIKE against the heavy read view. The base table
    shares the read view's id-space, so the ids returned feed straight into
    fetch_jobs_by_ids() for full enrichment. Titles are OR'd together and trimmed
    to 60 chars to keep the LIKE values bounded.
    """
    if not positions:
        return []

    c = config.COL
    pos_clauses = []
    params: dict = {}
    for i, pos in enumerate(positions):
        key = f"pos_{i}"
        pos_clauses.append(f"`{c['title']}` LIKE :{key}")
        params[key] = f"%{str(pos)[:60]}%"
    params["limit"] = limit

    sql = f"""
        SELECT `{c['job_id']}` AS id
        FROM {config.PROFILE.jobs_table}
        WHERE {' OR '.join(pos_clauses)}
        LIMIT :limit
    """

    with get_engine().connect() as conn:
        result = conn.execute(text(sql), params)
        return [row[0] for row in result]


# ─── Fetch by title + company (fallback when AI IDs are stale) ───────────────

def fetch_jobs_by_title_company(candidates: list[dict]) -> list[dict]:
    """
    For each {title, company} pair, find the best matching DB row.

    Title/company are matched on the base `jobs_table` (a fast indexed scan) to
    get an id, then the full row is enriched by id from the read view — same
    reason as fetch_jobs_for_matching: a leading-wildcard LIKE against the heavy
    view times out. Each returned row gets an extra '_matched_title' key with the
    original title used for lookup so the caller can map it back.
    """
    if not candidates:
        return []

    c = config.COL
    table = config.PROFILE.jobs_table

    import re as _re

    def _title_fragment(t: str) -> str:
        """Extract a short, searchable fragment from a job title."""
        # Split on common separators and take the first meaningful part
        fragment = _re.split(r'[/(,]', t)[0].strip()
        # Remove trailing punctuation and gender markers like *in, (m/w/d), etc.
        fragment = _re.sub(r'[\*\(].*$', '', fragment).strip()
        return fragment[:50] if fragment else t[:50]

    id_to_title: dict = {}   # resolved job id → the original title used to find it
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
                SELECT `{c['job_id']}` AS id
                FROM {table}
                WHERE `{c['title']}` LIKE :title
                {company_clause}
                ORDER BY `{c['job_id']}` DESC
                LIMIT 1
            """
            try:
                row = conn.execute(text(sql), params).first()
                if row is None and company:
                    # retry without company constraint
                    sql2 = f"""
                        SELECT `{c['job_id']}` AS id
                        FROM {table}
                        WHERE `{c['title']}` LIKE :title
                        ORDER BY `{c['job_id']}` DESC
                        LIMIT 1
                    """
                    row = conn.execute(text(sql2), {"title": f"%{fragment}%"}).first()
                if row is not None:
                    id_to_title.setdefault(row[0], title)
            except Exception:
                continue

    if not id_to_title:
        return []

    # One enrichment query for all resolved ids (already _add_geo'd inside).
    rows_out = fetch_jobs_by_ids(list(id_to_title.keys()))
    for r in rows_out:
        jid = r.get(c["job_id"])
        r["_matched_title"] = id_to_title.get(jid) or id_to_title.get(str(jid))
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
