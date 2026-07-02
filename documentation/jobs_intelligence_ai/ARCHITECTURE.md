# Jobs Intelligence AI — Architecture Overview

## System Summary

A Flask web application for a recruitment agency (Acme Recruitment). Staff log in,
enter a candidate profile (CV upload, free text, or LinkedIn import), and the system finds
matching job postings from a live market database. Staff then **save** the things worth
keeping — candidates, jobs, companies, and contacts — into a shared, company-scoped database
their colleagues also work from.

The app is **multi-country**: the same code serves Austria and Slovakia, selected at startup by
the `COUNTRY` env var (default `at`) or a CLI flag (`--sk` / `--country sk`). Everything
market-specific lives in a `Profile` (see `config/profiles.py`).

---

## Stack

| Layer        | Technology                                                        |
|--------------|-------------------------------------------------------------------|
| Backend      | Python 3.11+ · Flask (app factory + blueprints)                   |
| Databases    | AWS RDS MySQL · SQLAlchemy (`QueuePool`) — one market DB per country + one shared app DB |
| AI           | OpenAI Responses API (`responses.parse`, Structured Outputs) · `file_search` on a per-country vector store |
| Frontend     | Vanilla JS (ES modules, no build step) · plain CSS (IC brand palette) |
| Auth         | Session login · `account_company` (tenant) + `app_user` (staff) · `own`/`all` visibility |

---

## Directory Layout

```
src/jobs_intelligence_ai/
├── __main__.py             # `python -m jobs_intelligence_ai [--sk|--at|--country xx]`
├── config/
│   ├── settings.py         # env config; resolves the active Profile, re-exports COL/DB_URL/…
│   └── profiles.py         # per-country Profile: COL map, read_view, vector store env, feature flags
├── frontend/
│   ├── app.py              # create_app() factory: auth, login/logout, index, /debug/schema
│   ├── __init__.py         # register_blueprints()
│   ├── blueprints/         # route modules: search, saved, company, candidate,
│   │                       #   job_detail, interview, feedback
│   ├── templates/          # index.html (SPA shell), login.html
│   └── static/
│       ├── js/             # ES modules — boot.js is the entry point (see FRONTEND.md)
│       └── css/            # app.css (+ feedback.css, saved-dashboard.css)
├── infra/
│   └── database.py         # SQLAlchemy engine(s) + query helpers (get_engine, describe_view)
├── services/               # business logic, one package per concern:
│   │                       #   auth, candidate (incl. store.py), search, reporting,
│   │                       #   interview, enrichment, geo, stats, job_detail
│   └── …
└── shared/                 # cross-service helpers (e.g. shared.llm.get_client)

.env                        # API keys, DB URLs (DATABASE_URL / DATABASE_URL_SK), vector store ids — repo root, not committed
data/sql/app_schema_v2.sql  # canonical DDL for the app DB (see DATABASE.md)
```

There is **no** `core/`, `stats/` (top-level), `rag/`, `integrations/`, or `helpers/` package —
that was the pre-rework layout. Persistence lives in `services/candidate/store.py`, matching in
`services/search/`, and LLM report/summary code in `services/reporting/`.

---

## Two databases

The app talks to **two logical databases** over the same MySQL server:

1. **Market catalogue — one per country** (`Jobs_Intelligence_Austria` / `Jobs_Intelligence_Slovakia`).
   Holds the crawled market data: `jobs`, company data (`companies` in AT, `companies_finstat` in
   SK), `contacts`, and the `View_Jobs_*` read views the app queries. Fed by pipelines, read-only
   from the app's perspective. Selected per country via `Profile.db_schema` / `db_url_env`.

2. **App database — shared** (`Jobs_Intelligence_AI`, `config.APP_SCHEMA`). Holds everything the
   staff create: `account_company`, `app_user`, `saved_candidates`, `saved_jobs`,
   `saved_companies`, `saved_contacts`, `audit_log`, `feedback`. A `country` CHAR(2) **column**
   (not a table prefix) keeps Austrian and Slovak rows apart. Saved-* rows reference a market row
   by `(country, id)` — no cross-DB foreign key.

See [DATABASE.md](infra/DATABASE.md) for the full schema and column mappings.

---

## High-Level Data Flow

```
Staff browser (two tabs: Search · Saved)
      │
      │  Search: POST /api/match  { candidate_text, filters, top_n }
      ▼
  search blueprint ──► services/search
        │  OpenAI Responses API + file_search on the country's vector store
        │  → job ids resolved against the market DB (Profile.read_view)
        └► ranked jobs [{ job_id, title, company, salary, score, grade, … }]

      │  Click a company name → company panel
      ▼
  company blueprint
        ├─ GET /api/company/id?name=…   → { company_id }         (fast: id only, no LLM)
        └─ GET /api/company?name=…      → stats + AI hiring-profile summary + contacts
                                          (services/reporting.summarize_company — the slow call)

      │  Save something (candidate / job / company / contact)
      ▼
  saved blueprint ──► services/candidate/store
        └► INSERT into the app DB (owner_id + account_company_id + country + market row id),
           deduped; shows up in the Saved tab for the whole company (own/all visibility)
```

---

## Key Design Decisions

### Per-country profiles (`config/profiles.py`)
All market-specific config lives in a frozen `Profile`: the `COL` map (internal key → DB column),
the `read_view` / `jobs_table` to query, the DB-URL and vector-store env var names, the filter
dropdown SQL, and feature flags (`has_guided`, `has_map`, `has_analytics`, `has_occ_filter`).
`config.settings` picks the active profile from `COUNTRY` and re-exports its fields, so the rest of
the app uses `config.COL` / `config.DATABASE_URL` / `config.VECTOR_STORE_ID` unchanged. Austria and
Slovakia have genuinely different schemas — SK has no `occupational_group`, no `description`
(only `summary`), a different company table, and reads from `View_Jobs_Test` rather than
`View_Jobs_Full`. Columns absent in a country's view are listed in `Profile.absent_cols` and
gated by `col_present()` so a query never names a column that doesn't exist.

### Saved data is company-scoped + owner-tracked
Every saved row carries `account_company_id` (the hard privacy boundary — you never see another
company's data) and `owner_id` (the staff member who saved it). A user's `visibility` (`own`/`all`)
decides whether the Saved tab shows just their rows or all colleagues' rows within the company.
Dedup is enforced server-side by a `UNIQUE(owner_id, country, <ref_id>)` key plus a pre-insert
existence check.

### LLM calls use Structured Outputs
Service code calls the OpenAI Responses API via `shared.llm.get_client` and
`responses.parse(text_format=<schema>)`, returning validated objects — no hand-rolled JSON
parsing or "respond with ONLY JSON" prompts. Prompts and schemas live in each service's
`config.py`. See the per-service READMEs (e.g. `services/reporting/`, `services/candidate/`).

### Keyword fallback
If no OpenAI key is configured, matching falls back to keyword similarity computed against the
market DB, so basic demos work with no AI dependency.
