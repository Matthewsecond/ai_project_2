"""
profiles.py — Per-country configuration for the demo app.

The app is country-agnostic; everything market-specific lives in a Profile:
  - which DB schema / DATABASE_URL env / vector store env to use,
  - the COL mapping (View_Jobs_Full column → internal key),
  - the SQL behind the filter dropdowns (states / occ_groups / portals),
  - which text columns feed keyword fallback matching,
  - feature flags for the two Austria-only features (guided funnel, geo map),
  - display label + language for prompts.

Select the active profile with the COUNTRY env var (default "at"). config.py
reads everything below and re-exports it, so the rest of the app keeps using
config.COL / config.DATABASE_URL / config.VECTOR_STORE_ID unchanged.

Austria vs Slovakia differ in more than column names:
  - Slovakia has no `description` (only `summary` + `skills`), no
    `occupational_group`, no `original_salary`/`zipcode`/`order_number`.
  - Locations are region / city / municipality (vs AT location / zipcode), and
    salary carries an explicit `salary_currency`.
  - The guided funnel (German occupational_group taxonomy) and the Austrian
    Bundesland map have no SK equivalent yet, so both are flagged off for SK.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Profile:
    key:               str            # "at" / "sk"
    label:             str            # "Austria" / "Slovakia"
    demonym:           str            # adjective for prose: "Austrian" / "Slovak"
    language:          str            # prompt language hint: "de" / "sk"
    db_schema:         str            # MySQL schema holding the job data (View_Jobs_Full)
    app_schema:        str            # MySQL schema holding the app pipeline (candidates,
                                      # saved jobs, companies, targets, audit, feedback).
                                      # Same DB for both countries; tables are kept apart
                                      # by table_prefix below so AT and SK never mix.
    table_prefix:      str            # per-country table-name prefix in app_schema:
                                      # "" for Austria, "sk_" for Slovakia.
    db_url_env:        str            # env var holding the SQLAlchemy URL
    vector_store_env:  str            # env var holding the OpenAI vector store id
    currency:          str            # display currency symbol
    portal_pin:        str | None     # portal pinned to top of the dropdown
    has_guided:        bool           # guided funnel tab available?
    has_map:           bool           # report geo map available?
    has_analytics:     bool           # Opportunities Radar / Analytics mode available?
    has_occ_filter:    bool           # show the occupational-group filter dropdown?
    col:               dict           # internal key → DB column name
    filter_queries:    dict           # dropdown key → SQL ({db} = schema)
    match_text_cols:   tuple          # COL keys whose text feeds keyword fallback
    absent_cols:       frozenset = field(default_factory=frozenset)
                                      # COL keys whose mapped column does NOT exist in
                                      # this country's read_view. `SELECT *` reads
                                      # resolve them to None via row.get(...), but any
                                      # query that names the column explicitly (SELECT
                                      # list or WHERE) must skip it — see col_present().
    read_view:         str = "View_Jobs_Full"
                                      # The view the app reads full job records from.
                                      # View_Jobs_Full fans out by location (more rows than
                                      # jobs — deduped by id in fetch_jobs_by_ids) and its
                                      # per-row correlated subqueries make a leading-wildcard
                                      # LIKE time out; an id-IN lookup against it stays fast.
    jobs_table:        str = "jobs"
                                      # Base table (same id-space as read_view) used to
                                      # resolve a job title → id with a fast indexed scan,
                                      # instead of a leading-wildcard LIKE against the
                                      # heavy view.
    desc_lookup_sql:   str | None = None
                                      # Optional per-id scraped-description lookup ({db} =
                                      # schema, {ids} = IN-list placeholders; must return
                                      # job_id + description columns). Set when the read_view
                                      # has no description column but the base tables carry
                                      # one (SK) — see infra.database._add_scraped_descriptions.
    industry_lookup_sql: str | None = None
                                      # Optional per-company NACE/industry lookup ({db} =
                                      # schema, {ids} = company_id IN-list placeholders; must
                                      # return company_id/industry_code/industry_text). Set
                                      # when the read_view carries no industry data of its own
                                      # (AT — industry lives in companies_creditreform, joined
                                      # by company_id). SK's read_view already carries
                                      # company_sk_nace/company_sk_nace_text directly, so it
                                      # leaves this unset — see infra.database._add_industry.
    has_staffing_filter: bool = False
                                      # Show "Exclude Personnel Service Providers"? Only SK's
                                      # companies_finstat carries personal_service_provider —
                                      # AT has no equivalent flag.

    def col_present(self, key: str) -> bool:
        """True if COL[key] is a real column in this profile's View_Jobs_Full.

        SQL builders that put a column in the SELECT list or WHERE clause must
        gate on this; otherwise the query 500s on countries where the column is
        absent (e.g. Slovakia has no `occupational_group`)."""
        return key not in self.absent_cols


# ── Austria ──────────────────────────────────────────────────────────────────

_AT_COL = {
    # Identity
    "job_id":        "id",
    "title":         "position",
    "company":       "company_crawler_name",
    "description":   "description",
    "summary":       "summary",
    # Location
    "state":         "location",
    "city":          "city",
    "municipality":  "municipality",
    "zipcode":       "zipcode",
    "detailed_location": "detailed_location",
    # Salary
    "salary":        "salary",
    "salary_type":   "salary_type",
    "original_salary": "original_salary",
    # Employment
    "work_time":     "work_time",
    "employment_relationship": "employment_relationship",
    "education":     "education",
    # Dates
    "date_posted":   "publication_date",
    "application_deadline": "application_deadline",
    "start_timeline": "start_timeline",
    # Links & meta
    "url":           "cleaned_link",
    "portal":        "portal",
    "order_number":  "order_number",
    "occ_group":     "occupational_group",
    "status":        "status",
    # Skills & contacts
    "skills":        "skills",
    "skills_en":     "skills_english",
    "contacts":      "contacts",
    # Not in view (keep for fallback)
    "esco_skills":   "esco_skills",
    "lat":           "latitude",
    "lon":           "longitude",
}

_AT_FILTER_QUERIES = {
    "states": """
        SELECT DISTINCT l.location
        FROM {db}.locations l
        INNER JOIN {db}.jobs j ON j.location_id = l.id
        WHERE j.status IN ('new','updated')
          AND l.location IS NOT NULL
        ORDER BY l.location
    """,
    # Only groups with >= 10 active jobs, sorted by frequency, max 300.
    "occ_groups": """
        SELECT j.occupational_group
        FROM {db}.jobs j
        WHERE j.status IN ('new','updated')
          AND j.occupational_group IS NOT NULL
          AND j.occupational_group != 'keine Zuordnung'
        GROUP BY j.occupational_group
        HAVING COUNT(*) >= 10
        ORDER BY COUNT(*) DESC
        LIMIT 300
    """,
    "portals": """
        SELECT DISTINCT j.portal
        FROM {db}.jobs j
        WHERE j.status IN ('new','updated')
          AND j.portal IS NOT NULL
        ORDER BY j.portal
    """,
    # work_time/employment_relationship/education are messy AMS free-text fields —
    # many jobs store a comma-joined combination (e.g. "Lehre/Lehre mit
    # Meisterprüfung, Matura"), which pushes raw distinct counts into the
    # hundreds/thousands. The frequency cut (same shape as occ_groups above) keeps
    # the dropdown to the handful of values that actually cover most postings.
    "work_time": """
        SELECT j.work_time
        FROM {db}.jobs j
        WHERE j.status IN ('new','updated')
          AND j.work_time IS NOT NULL AND j.work_time != ''
        GROUP BY j.work_time
        HAVING COUNT(*) >= 20
        ORDER BY COUNT(*) DESC
    """,
    "employment_relationship": """
        SELECT j.employment_relationship
        FROM {db}.jobs j
        WHERE j.status IN ('new','updated')
          AND j.employment_relationship IS NOT NULL AND j.employment_relationship != ''
        GROUP BY j.employment_relationship
        HAVING COUNT(*) >= 20
        ORDER BY COUNT(*) DESC
    """,
    "education": """
        SELECT j.education
        FROM {db}.jobs j
        WHERE j.status IN ('new','updated')
          AND j.education IS NOT NULL AND j.education != ''
        GROUP BY j.education
        HAVING COUNT(*) >= 20
        ORDER BY COUNT(*) DESC
    """,
    # NACE/industry — Austria's read_view has no industry column, so the dropdown
    # (like the row-level lookup) reads companies_creditreform directly.
    "nace": """
        SELECT DISTINCT industry_code, industry_text
        FROM {db}.companies_creditreform
        WHERE industry_code IS NOT NULL AND industry_code != ''
        ORDER BY industry_code
    """,
}

# Per-company NACE/industry lookup, joined in by company_id after the main fetch
# (see infra.database._add_industry) — the read_view itself carries no industry data.
_AT_INDUSTRY_LOOKUP_SQL = """
    SELECT id AS company_id, industry_code, industry_text
    FROM {db}.companies_creditreform
    WHERE id IN ({ids})
"""

AUSTRIA = Profile(
    key              = "at",
    label            = "Austria",
    demonym          = "Austrian",
    language         = "de",
    db_schema        = "Jobs_Intelligence_Austria",
    app_schema       = "Jobs_Intelligence_AI",      # shared pipeline DB
    table_prefix     = "",                          # Austria uses the unprefixed tables
    db_url_env       = "DATABASE_URL",
    vector_store_env = "VECTOR_STORE_ID",
    currency         = "€",
    portal_pin       = "ams",
    has_guided       = True,
    has_map          = True,
    has_analytics    = True,
    has_occ_filter   = True,
    col              = _AT_COL,
    filter_queries   = _AT_FILTER_QUERIES,
    match_text_cols  = ("title", "occ_group", "description", "esco_skills"),
    industry_lookup_sql = _AT_INDUSTRY_LOOKUP_SQL,
    has_staffing_filter = False,   # no personal_service_provider equivalent for AT
)


# ── Slovakia ─────────────────────────────────────────────────────────────────
# The Slovak DB (cluster endpoint) has a different schema from Austria:
#   - View_Jobs_Full has `region` + `summary`, but NO `description` / `location`.
#   - `jobs` has no `location_id` (locations link via a junction), so the states
#     dropdown reads the kraje straight from `locations.region`.
#   - no `occupational_group` (so the occ-group filter is hidden), and salary
#     carries an explicit `salary_currency`.
# Columns absent from the SK view keep their conventional name and resolve to None
# via row.get(...). `description` maps to `summary` so description-driven UI still
# shows text.

_SK_COL = {
    # Identity
    "job_id":        "id",
    "title":         "position",
    "company":       "company_crawler_name",
    "description":   "summary",        # View_Jobs_Full has `summary`, no `description`
    "summary":       "summary",        # both description-driven keys surface `summary`
    # Location
    "state":         "region",         # the kraje
    "city":          "city",
    "municipality":  "municipality",
    "zipcode":       "zipcode",         # absent → None
    "detailed_location": "detailed_location",
    # Salary
    "salary":        "salary",
    "salary_type":   "salary_type",
    "original_salary": "original_salary",   # absent → None
    "salary_currency": "salary_currency",   # SK-specific
    # Employment
    "work_time":     "work_time",
    "employment_relationship": "contract_type",
    "education":     "education",
    # Dates
    "date_posted":   "publication_date",
    "application_deadline": "application_deadline",
    "start_timeline": "start_timeline",
    # Links & meta
    "url":           "url",                 # View_Jobs_Test exposes `url` (no cleaned_link)
    "portal":        "portal",
    "order_number":  "order_number",        # absent → None
    "occ_group":     "occupational_group",  # absent → None
    "status":        "status",
    # Skills & contacts
    "skills":        "skills",
    "skills_en":     "skills_english",
    "contacts":      "contacts",            # View_Jobs_Full has a real `contacts` column;
                                            # _serialize_job also falls back to the split
                                            # contact_name/mail/phone if it's ever absent
    "languages":     "languages",           # SK-specific
    # Not in view (keep for fallback)
    "esco_skills":   "esco_skills",
    "lat":           "latitude",
    "lon":           "longitude",
}

_SK_FILTER_QUERIES = {
    # The kraje come straight from the base `locations` table — fast, and the SK
    # `jobs` table has no location_id to join on. occ_groups has no SK equivalent.
    "states": """
        SELECT DISTINCT region
        FROM {db}.locations
        WHERE region IS NOT NULL AND region <> ''
        ORDER BY region
    """,
    "portals": """
        SELECT DISTINCT portal
        FROM {db}.jobs
        WHERE status IN ('new','updated')
          AND portal IS NOT NULL
        ORDER BY portal
    """,
    # SK's work_time/contract_type/education are a clean small taxonomy (a handful
    # of distinct values), unlike AT's messier combined strings — the frequency cut
    # is a no-op here but keeps the query shape identical across both profiles.
    # NOTE: employment_relationship maps to the `contract_type` column (see _SK_COL).
    "work_time": """
        SELECT work_time
        FROM {db}.jobs
        WHERE status IN ('new','updated')
          AND work_time IS NOT NULL AND work_time != ''
        GROUP BY work_time
        HAVING COUNT(*) >= 20
        ORDER BY COUNT(*) DESC
    """,
    "employment_relationship": """
        SELECT contract_type
        FROM {db}.jobs
        WHERE status IN ('new','updated')
          AND contract_type IS NOT NULL AND contract_type != ''
        GROUP BY contract_type
        HAVING COUNT(*) >= 20
        ORDER BY COUNT(*) DESC
    """,
    "education": """
        SELECT education
        FROM {db}.jobs
        WHERE status IN ('new','updated')
          AND education IS NOT NULL AND education != ''
        GROUP BY education
        HAVING COUNT(*) >= 20
        ORDER BY COUNT(*) DESC
    """,
    # NACE/industry — SK's read_view already carries company_sk_nace/_text directly
    # (no per-row lookup needed, unlike AT), so the dropdown reads it from companies_finstat.
    "nace": """
        SELECT DISTINCT sk_nace AS industry_code, sk_nace_text AS industry_text
        FROM {db}.companies_finstat
        WHERE sk_nace IS NOT NULL AND sk_nace != ''
        ORDER BY sk_nace
    """,
}

SLOVAKIA = Profile(
    key              = "sk",
    label            = "Slovakia",
    demonym          = "Slovak",
    language         = "sk",
    db_schema        = "Jobs_Intelligence_Slovakia",
    app_schema       = "Jobs_Intelligence_AI",      # same pipeline DB as Austria
    table_prefix     = "sk_",                        # SK uses sk_-prefixed tables
    db_url_env       = "DATABASE_URL_SK",
    vector_store_env = "VECTOR_STORE_ID_SK",
    currency         = "€",
    portal_pin       = None,    # "ams" is Austria-only
    has_guided       = False,   # German occupational_group taxonomy — no SK equivalent
    has_map          = False,   # Austrian Bundesland polygons — no SK kraj geometry yet
    has_analytics    = False,   # Radar/Analytics is built on occupational_group + AT joins
    has_occ_filter   = False,   # SK has no occupational_group → hide that dropdown
    col              = _SK_COL,
    filter_queries   = _SK_FILTER_QUERIES,
    match_text_cols  = ("title", "summary", "skills", "skills_en"),
    # The Slovak app reads from View_Jobs_Full and resolves titles → ids on its base
    # table jobs. The vector store (~22k indexed jobs) long ago outgrew the old
    # jobs_test/View_Jobs_Test subset (~2.7k), which silently dropped ~85% of matches
    # at id-lookup time; the full view resolves them all. Id-`IN` lookups against the
    # view stay fast; the hot matching path only ever hits it by id.
    read_view        = "View_Jobs_Full",
    jobs_table       = "jobs",
    # Columns View_Jobs_Full does not have. They keep their conventional names in
    # _SK_COL so `SELECT *` reads resolve to None, but explicit SELECT/WHERE
    # references must be skipped (see col_present()).
    absent_cols      = frozenset({"occ_group", "original_salary", "zipcode",
                                  "order_number"}),
    # ~45% of active SK jobs have a full scraped description in the base tables
    # (19.6k of 43.6k, 2026-07-02). View_Jobs_Full only carries the short `summary`,
    # and View_Jobs_Descriptions (which joins them in) is far too slow to scan —
    # so the app fetches descriptions per id and falls back to `summary` otherwise.
    desc_lookup_sql  = """
        SELECT djj.job_id AS job_id, MIN(d.description) AS description
        FROM {db}.description_jobs_junction djj
        JOIN {db}.descriptions d ON d.id = djj.description_id
        WHERE djj.job_id IN ({ids})
        GROUP BY djj.job_id
    """,
    has_staffing_filter = True,   # companies_finstat.personal_service_provider
)


# ── Registry ─────────────────────────────────────────────────────────────────

PROFILES: dict[str, Profile] = {AUSTRIA.key: AUSTRIA, SLOVAKIA.key: SLOVAKIA}
DEFAULT_COUNTRY = AUSTRIA.key


def get_profile(country: str) -> Profile:
    return PROFILES.get((country or DEFAULT_COUNTRY).lower(), AUSTRIA)
