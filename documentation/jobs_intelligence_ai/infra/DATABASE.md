# Database Design

The app talks to **two logical databases** on the same AWS RDS MySQL server:

1. **Market catalogue — one schema per country** (`Jobs_Intelligence_Austria` /
   `Jobs_Intelligence_Slovakia`): the crawled job data, read-only from the app.
2. **App database — shared** (`Jobs_Intelligence_AI`): everything staff create/save.

Connection URLs live in `.env`:

| Env var             | Used for                                            |
|---------------------|-----------------------------------------------------|
| `DATABASE_URL`      | Austria market DB (`Jobs_Intelligence_Austria`)     |
| `DATABASE_URL_SK`   | Slovakia market DB (`Jobs_Intelligence_Slovakia`)   |

The active market DB is chosen by the country profile (`Profile.db_url_env`). The app DB schema
name is `config.APP_SCHEMA` (`Jobs_Intelligence_AI`) and is shared by both countries. SQLAlchemy
uses a `QueuePool`; the engine is obtained via `infra.database.get_engine()`.

---

## Market read view: `read_view`

The app reads full job records from a per-country view (`Profile.read_view`) and resolves a job
title → id against a per-country base table (`Profile.jobs_table`):

| Country  | `read_view`      | `jobs_table` | Why                                                            |
|----------|------------------|--------------|---------------------------------------------------------------|
| Austria  | `View_Jobs_Full` | `jobs`       | Full view.                                                     |
| Slovakia | `View_Jobs_Full` | `jobs`       | Full view (~151k ids). The vector store (~22k indexed jobs) outgrew the old `View_Jobs_Test`/`jobs_test` subset (~2.7k), which silently dropped ~85% of matches at id-lookup time. `View_Jobs_Full` fans out by location (so `fetch_jobs_by_ids` dedups by id) and its per-row subqueries make a leading-wildcard `LIKE` time out; id-`IN` lookups — the hot matching path — stay fast. |

### Column mapping (`config.COL`, from the active `Profile`)

All SQL column references go through `config.COL[...]` so a view rename touches one dict. The
mapping differs by country; **Austria**:

| Config key                | AT column (`View_Jobs_Full`) | Notes                                  |
|---------------------------|------------------------------|----------------------------------------|
| `job_id`                  | `id`                         | Primary key                            |
| `title`                   | `position`                   | Job title                              |
| `company`                 | `company_crawler_name`       | Employer name (from crawler)           |
| `description`             | `description`                | Full text (often null)                 |
| `summary`                 | `summary`                    | LLM-generated summary                  |
| `state`                   | `location`                   | Austrian Bundesland                    |
| `city`                    | `city`                       | City / district                        |
| `salary`                  | `salary`                     | Monthly salary as string (often null)  |
| `salary_type`             | `salary_type`                |                                        |
| `work_time`               | `work_time`                  | e.g. "Vollzeit"                        |
| `employment_relationship` | `employment_relationship`    |                                        |
| `date_posted`             | `publication_date`           |                                        |
| `url`                     | `cleaned_link`               | Job posting URL                        |
| `portal`                  | `portal`                     | ams / karriere / stepstone …           |
| `occ_group`               | `occupational_group`         | AMS taxonomy                           |
| `status`                  | `status`                     | new / updated / outdated               |
| `skills` / `skills_en`    | `skills` / `skills_english`  | Comma-separated strings                |
| `lat` / `lon`             | `latitude` / `longitude`     | If geocoded                            |

**Slovakia** differs in more than names — key overrides in `_SK_COL`: `state`→`region` (kraje),
`summary`/`description`→`summary` (`View_Jobs_Full` has `summary`, no `description`),
`employment_relationship`→`contract_type`, plus SK-only `salary_currency` and `languages`.
Columns absent from the SK view are listed in `Profile.absent_cols`
(`occ_group`, `original_salary`, `zipcode`, `order_number`) and gated by
`Profile.col_present()` — a `SELECT *` read resolves them to `None`, but any query naming the
column in a SELECT/WHERE must skip it.

---

## Company identity (per country)

A crawler company name resolves to a stable market id differently per country. The company panel
resolves it best-effort in three tiers (`company.py::_resolve_company_id`), each isolated so a
missing table in one country doesn't abort the others:

| Tier | Source                                            | Applies to |
|------|---------------------------------------------------|------------|
| 1    | `companies.id WHERE company_crawler_name = :n`    | Austria    |
| 2    | `View_Jobs_Full.company_id` for the crawler name  | Austria (name-mismatch fallback) |
| 3    | `jobs.companies_finstat_id` (FK → `companies_finstat.id`) | Slovakia — has **no** `companies` table and **no** `View_Jobs_Full.company_id`; company data lives in `companies_finstat`, joined to jobs by `companies_finstat_id` |

The resolved id is stored as `saved_companies.target_company_id`. `GET /api/company/id` returns
just this id (fast); `GET /api/company` also returns it alongside the full profile.

### Contacts

- **Austria:** `View_Jobs_Contacts` (contact ↔ job, with name/email/phone/linkedin).
- **Slovakia:** no such view — contacts come from `contact_jobs_junction` joined to `contacts`
  and `jobs`. Saved as `saved_contacts.contact_id`.

---

## App database (`Jobs_Intelligence_AI`)

Canonical DDL: [`data/sql/app_schema_v2.sql`](../../../data/sql/app_schema_v2.sql). The live tables
are **ahead** of that file (extra columns such as `snapshot`/`extras`; `saved_jobs.status` is
VARCHAR not ENUM) — treat the SQL as a baseline, not a byte-for-byte mirror.

```
account_company (tenant: the firm whose staff log in)
   └─ app_user (a login; role admin|member, visibility own|all)
        ├─ saved_candidates  — the ONE normal app-owned table (full candidate record)
        ├─ saved_jobs        — job saved FOR a saved_candidate (status new..won/lost)
        ├─ saved_companies   — bookmarked target company (target_company_id → market)
        └─ saved_contacts    — bookmarked person       (contact_id → market)
audit_log · feedback         — cross-cutting
```

Key points:
- Every saved-* row carries `account_company_id` (privacy boundary), `owner_id` (who saved it),
  and `country` CHAR(2) (`at`|`sk`). The `country` **column** — not a table prefix — keeps the two
  markets apart.
- The saved junctions store only `(owner_id, country, <market row id>)` + a little metadata/snapshot;
  they don't copy catalogue data. References are logical `(country, id)` — no cross-DB FK.
- Dedup: `UNIQUE(owner_id, country, target_company_id)` on `saved_companies`, and the analogous key
  on `saved_contacts` / `saved_jobs`, plus a pre-insert existence check in `store.py`.
- Seeded: `account_company` id=1 "Acme Recruitment" + three logins
  (`admin`/`Monika2`/`hr_manager`). A backup of the pre-rework app DB is in schema
  `Jobs_Intelligence_AI_prerework`.
- **Cutover complete (2026-07-02):** the old tables (`candidate`, `sk_candidate`,
  `candidate_saved_job`, `sk_candidate_saved_job`, `candidate_company`, `sk_candidate_company`,
  `company`, `sk_company`, `target_candidate`, `sk_target_candidate`, `users`, `sk_feedback`,
  `sk_audit_log`) were dropped after checksum-verification against the prerework backup. The
  live schema is mirrored byte-for-byte in [`data/sql/app_schema_v2.sql`](../../../data/sql/app_schema_v2.sql).

Persistence layer: `services/candidate/store.py` (`add_saved_company` / `add_saved_contact` /
`list_saved_*` / `delete_saved_*`, plus the candidate + saved-job functions).

---

## Salary data quality

Salary coverage is partial — many rows have `salary = NULL`. Values are stored as plain strings
representing monthly EUR ("2400"); some outliers are annual figures in the same field. The
`/api/salary_stats` endpoint excludes values `< €200` and trims the top 2% to remove outliers.

---

## Vector store

Each country has its own OpenAI vector store, named by `Profile.vector_store_env`
(`VECTOR_STORE_ID` for Austria, `VECTOR_STORE_ID_SK` for Slovakia) and read via
`config.VECTOR_STORE_ID`. Jobs are indexed as text documents; the `file_search` tool retrieves
semantically relevant jobs for a candidate query, and the returned ids are resolved against the
market DB (the source of truth for structured fields). The vector store and MySQL can drift if a
job is added/removed from one but not the other.

---

## Schema check

After a market-DB change, compare the live columns against `config.COL`:

```
GET http://localhost:5000/debug/schema      # DESCRIBE the active read_view
```
