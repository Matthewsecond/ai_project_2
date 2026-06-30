# Rework Plan — Database Layout + Frontend

> **Status:** PLANNING (active). Started 2026-06-29. Succeeds
> [RESTRUCTURE_PLAN.md](RESTRUCTURE_PLAN.md), which is **COMPLETE** (the modular
> backend/frontend restructure — Stages 1–2.6 — is done). This plan covers the next
> phase: turning the lean app into the IC product. **Two tracks, done in order —
> A. database layout rework first** (the backend structure), **then B. frontend rework**
> (IC rebrand + new information architecture) on top of it.
>
> **STANDING RULE — docs track the code.** After each step lands, update this plan's
> checkboxes/decisions log and the mirrored module docs as part of that step. A step
> isn't "done" until its docs are current.

---

## 1. Why we're doing this

The restructure left us with a clean, modular codebase (foundation + self-contained
service modules + a modular frontend). What it deliberately deferred — under the old
plan's "Stage 3" — is the **product**: the **data model** that the current cryptic `sk_*`
tables don't support (no real users, no collaboration, no audit), and then how the shipped
app looks (IC branding) and is organised (the tabs/areas a user works in).

Two inputs drive this plan:
- A product sketch from the client describing two areas — a **Tables** (data) side and a
  **Sales View** (working tool) side — with saved jobs/candidates/contacts and multi-user
  collaboration.
- The IC brand palette (from `project_controlling`) — see [§4.1](#41-ic-rebrand).

**We do the database first** so the backend structure (users, companies, saved items,
access rules) exists before we build the UI that depends on it.

## 2. Scope — two tracks, in order

| Order | Track | Focus | Coupling |
|---|---|---|---|
| **1st** | **A. Database layout rework** | Clean schema, country unification, users + collaboration + audit | The backend foundation everything else builds on |
| **2nd** | **B. Frontend rework** | IC rebrand, new IA, expanded filters, new tabs | New tabs depend on Track A |

The only frontend piece independent of the DB is the **IC rebrand** (pure CSS, [§4.1](#41-ic-rebrand)) —
it can land anytime. Everything involving clients/contacts/users (new tabs + collaboration)
is gated on Track A landing first.

Branch model is unchanged from [RESTRUCTURE_PLAN.md §2](RESTRUCTURE_PLAN.md): `master` is
the lean base, `develop` adds features on top, promotion is per-feature folder. The
lean-snapshot composition for `master` (foundation + search/candidate/saved/job_detail +
support; `interview`/`clustering` held back) is the deployment target for this work.

---

## 3. Track A (first) — Database layout rework

### 3.1 Problem with today's schema
Tables are country-prefixed and cryptic (`sk_candidate`, `sk_company`, …), there's no real
user/account model (only `SEED_USERS` for login), no notion of who saved what, and no audit
trail. Matching reads from per-country views (`View_Jobs_*`).

### 3.2 Target schema (greenfield `Jobs_Intelligence_AI`)

This is a **greenfield rebuild of the app DB only** (the `Jobs_Intelligence_AI` schema, audited
2026-06-30). The **market data stays in the per-country DBs** (`Jobs_Intelligence_Austria` /
`Jobs_Intelligence_Slovakia`) — `jobs`, `companies`, `contacts` are the shared catalogue, fed by
pipelines and read via the `View_Jobs_*` views. The app DB references those by id (no cross-DB FK).

Shape of the model:
- **Tenanting:** `account_company` (the firm) → `app_user` (its staff).
- **`saved_candidates` is a normal table** holding the **full candidate record** — staff create it
  (CV upload); there is no external candidate catalogue to reference. Company-owned: carries
  `account_company_id` (privacy boundary) + `owner_id` (the employee who tracks it).
- **`saved_jobs` / `saved_companies` / `saved_contacts` are thin junction / reference tables** — they
  don't copy catalogue data, they link a user to a market row (`owner_id` + `country` + the row's id
  + a little metadata). `saved_jobs` also links to a `saved_candidate` ("this job, *for* this
  candidate") and carries the Won/Lost placement `status`.
- **Country** is a `char(2)` column (`'at'`/`'sk'`), replacing the old `sk_` table prefix.

```
APP DB — Jobs_Intelligence_AI
=============================
account_company
  └─(1:N)─ app_user                 role: admin|member,  visibility: own|all
             │  owns (owner_id, 1:N):
             ├─ saved_candidates    [NORMAL table — full candidate record]
             ├─ saved_jobs          (saved_candidate_id -> saved_candidates,
             │                        job_id -> jobs*, status: new..won|lost)
             ├─ saved_companies     (target_company_id -> companies*)
             ├─ saved_contacts      (contact_id -> contacts*)
             ├─ audit_log           (user_id)
             └─ feedback            (user_id)

job_vs_sync  (job_id -> file_id)    [vector-store sync — separate matching layer, kept as-is]

MARKET CATALOGUE — per-country DBs (Jobs_Intelligence_Austria / _Slovakia)
==========================================================================
jobs   ·   companies   ·   contacts

Legend:  ->  FK inside the app DB      *  logical ref into a market DB (country + id, no FK)
         saved_candidates = full record;  saved_* = thin junctions (link + a little metadata)
```

```sql
-- Tenant + users -------------------------------------------------------------
CREATE TABLE account_company (              -- the firm whose staff log in
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name        VARCHAR(255)    NOT NULL,
  created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE app_user (                     -- a person who logs in; one company
  id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  account_company_id BIGINT UNSIGNED NOT NULL,
  username           VARCHAR(128)    NOT NULL,
  password_hash      VARCHAR(255)    NOT NULL,
  display_name       VARCHAR(255)    NOT NULL DEFAULT '',
  email              VARCHAR(255)    NULL,
  role               ENUM('admin','member') NOT NULL DEFAULT 'member',
  visibility         ENUM('own','all')      NOT NULL DEFAULT 'all',
  created_at         DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_user_username (username),
  CONSTRAINT fk_user_company FOREIGN KEY (account_company_id) REFERENCES account_company (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- The candidate record (normal table — full data, app-owned) -----------------
CREATE TABLE saved_candidates (             -- staff-created; company-owned, user-tracked
  id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  account_company_id BIGINT UNSIGNED NOT NULL,           -- privacy boundary
  owner_id           BIGINT UNSIGNED NOT NULL,           -- the employee who owns it
  country            CHAR(2)         NOT NULL,           -- 'at' | 'sk'  (replaces sk_ prefix)
  full_name          VARCHAR(255)    NOT NULL,
  email              VARCHAR(255)    NULL,
  phone              VARCHAR(64)     NULL,
  linkedin           VARCHAR(512)    NULL,
  headline           VARCHAR(512)    NULL,
  location           VARCHAR(255)    NULL,
  seniority          VARCHAR(32)     NULL,
  years_experience   INT             NULL,
  industry           VARCHAR(255)    NULL,
  current_company    VARCHAR(255)    NULL,
  status             VARCHAR(32)     NOT NULL DEFAULT 'New',   -- candidate hiring status
  source             ENUM('cv_upload','manual','imported') NOT NULL DEFAULT 'cv_upload',
  is_template        TINYINT(1)      NOT NULL DEFAULT 0,
  skills             JSON NULL,  experiences JSON NULL,  education JSON NULL,   -- enrichment
  certifications     JSON NULL,  top_skills  JSON NULL,  strengths JSON NULL,   -- (carried over)
  ai_summary         TEXT NULL,  raw_profile JSON NULL,
  enriched_at        DATETIME NULL, ai_model VARCHAR(64) NULL,
  created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_cand_company (account_company_id),
  KEY ix_cand_owner   (owner_id),
  KEY ix_cand_country (country),
  CONSTRAINT fk_cand_company FOREIGN KEY (account_company_id) REFERENCES account_company (id),
  CONSTRAINT fk_cand_owner   FOREIGN KEY (owner_id)           REFERENCES app_user (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- User-owned saved references (thin junctions into the market catalogue) -----
CREATE TABLE saved_jobs (                   -- a job shortlisted FOR a saved candidate
  id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  account_company_id BIGINT UNSIGNED NOT NULL,
  owner_id           BIGINT UNSIGNED NOT NULL,           -- who saved/owns it
  saved_candidate_id BIGINT UNSIGNED NOT NULL,           -- which candidate it's for
  country            CHAR(2)         NOT NULL,           -- which market the job is from
  job_id             BIGINT UNSIGNED NOT NULL,           -- logical ref -> <country DB>.jobs (no cross-DB FK)
  status             ENUM('new','in_progress','proposal_sent','won','lost') NOT NULL DEFAULT 'new',
  score              DECIMAL(5,4)    NULL,
  grade              CHAR(1)         NULL,
  job_snapshot       JSON            NULL,               -- job fields at save time
  notes              TEXT            NULL,
  saved_at           DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_saved_jobs (saved_candidate_id, country, job_id),
  KEY ix_sj_owner (owner_id),
  CONSTRAINT fk_sj_company   FOREIGN KEY (account_company_id) REFERENCES account_company (id),
  CONSTRAINT fk_sj_owner     FOREIGN KEY (owner_id)           REFERENCES app_user (id),
  CONSTRAINT fk_sj_candidate FOREIGN KEY (saved_candidate_id) REFERENCES saved_candidates (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE saved_companies (              -- a target company a user bookmarked
  id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  account_company_id BIGINT UNSIGNED NOT NULL,
  owner_id           BIGINT UNSIGNED NOT NULL,
  country            CHAR(2)         NOT NULL,
  target_company_id  BIGINT UNSIGNED NOT NULL,           -- logical ref -> <country DB>.companies
  notes              TEXT            NULL,
  saved_at           DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_saved_companies (owner_id, country, target_company_id),
  CONSTRAINT fk_sc_company FOREIGN KEY (account_company_id) REFERENCES account_company (id),
  CONSTRAINT fk_sc_owner   FOREIGN KEY (owner_id)           REFERENCES app_user (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE saved_contacts (               -- a contact (person at a company) a user bookmarked
  id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  account_company_id BIGINT UNSIGNED NOT NULL,
  owner_id           BIGINT UNSIGNED NOT NULL,
  country            CHAR(2)         NOT NULL,
  contact_id         BIGINT UNSIGNED NOT NULL,           -- logical ref -> <country DB>.contacts
  notes              TEXT            NULL,
  saved_at           DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_saved_contacts (owner_id, country, contact_id),
  CONSTRAINT fk_sct_company FOREIGN KEY (account_company_id) REFERENCES account_company (id),
  CONSTRAINT fk_sct_owner   FOREIGN KEY (owner_id)           REFERENCES app_user (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Cross-cutting --------------------------------------------------------------
CREATE TABLE audit_log (
  id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  account_company_id BIGINT UNSIGNED NULL,
  user_id            BIGINT UNSIGNED NULL,               -- the actor
  action             VARCHAR(64)     NOT NULL,
  entity_type        VARCHAR(64)     NULL,               -- 'saved_candidate' | 'saved_job' | ...
  entity_id          BIGINT UNSIGNED NULL,
  detail             TEXT            NULL,
  created_at         DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_audit_company (account_company_id),
  KEY ix_audit_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE feedback (
  id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  account_company_id BIGINT UNSIGNED NULL,
  user_id            BIGINT UNSIGNED NULL,
  message            TEXT            NOT NULL,
  context            VARCHAR(64)     NULL,
  created_at         DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Vector-store sync (matching infrastructure — kept as-is, its own layer, NOT market catalogue):**
`job_vs_sync` + `sk_job_vs_sync` map each market `job_id` → its OpenAI vector-store `file_id`. This
is core matching/VS functionality that sits beside the app tables; left untouched (re-syncing would
re-upload ~11k files).

**Dropped / folded in:** the old `sk_*` duplicates (→ `country` column); `candidate_company`
(work history lives in `saved_candidates.experiences` JSON); the old empty `company` table (it was
LinkedIn past-employers, not a target company); `target_candidate` (keep only if the
guided-search "ideal candidate" draft feature stays — TBD).

**Resolved (2026-06-30):** (1) **contacts are catalogue-saved** — `saved_contacts` references the
country-DB `contacts`; no hand-created `contact` table for now (add later only if staff need it).
(2) **`job_id` is `BIGINT`** (market `jobs.job_id` is `INT`).

The runnable canonical version of this DDL lives at
[`data/sql/app_schema_v2.sql`](../../../data/sql/app_schema_v2.sql) (status: not yet applied;
backup in schema `Jobs_Intelligence_AI_prerework`).

### 3.3 Access & collaboration model
The tool promotes collaboration: by default users see every other user's saved data. The
fine-grained per-member grant was dropped as unnecessary (boss decision, 2026-06-29).

- `app_user.role`: `admin | member`.
- `app_user.visibility`: `own | all`.
  - `all` (default) — own + every other user's data **within the same `account_company`**.
  - `own` — only their own records (an opt-out switch if a user shouldn't see others).
- **The company boundary is always enforced.** A user only ever sees `saved_candidates` and the
  saved items belonging to their own `account_company` — never another company's. `all` vs `own`
  only widens/narrows visibility *within* that boundary.
- **How the boundary is enforced depends on the table:**
  - *`saved_candidates`* (full app-owned record): the `account_company_id` column is the hard wall;
    `own` shows rows where `owner_id` = viewer, `all` shows any owner in the company.
  - *Saved junctions* (`saved_jobs` / `saved_companies` / `saved_contacts`): same rule — filter on
    `account_company_id` + the row's `owner_id` (`own`/`all`).
  - *Market catalogue* (`jobs`, `companies`, `contacts` in the per-country DBs): visible to everyone;
    nothing private there — what's company-private is who *owns/saved* a reference to it.

How a viewer's access to a `saved_*` row resolves:

```
              viewer opens a saved_* row
                         │
                         ▼
          owner in the SAME account_company?
                 │                   │
                 no                  yes
                 │                   │
                 ▼                   ▼
              hidden        viewer's visibility?
                                 │            │
                                own          all
                                 │            │
                                 ▼            ▼
                           only rows      all colleagues'
                           you own        rows in the company
```

### 3.4 Migration approach
**Phased and non-destructive — the old `sk_*` tables are dropped, but only as the final
step, never up front and never via an in-place rename.** Each phase is reversible until the
drop:

1. **Add** the new tables/columns alongside the old ones (nothing removed yet).
2. **Backfill** the new tables from the existing `sk_*` data.
3. **Switch reads** (and writes) to the new tables; old tables now untouched but still present.
4. **Verify** — Stage 2.0 equivalence tests + `_fake_db` green, app exercised, a DB backup taken.
5. **Drop the old tables** — last, only once 1–4 hold. Optionally rename to `*_old` for a grace
   period first, then drop.

- **Don't drop blind:** anything that lives only in an old table must be backfilled before its
  table goes (Phase 2 gates Phase 5).
- **Special case — `View_Jobs_*`:** the vector-store-aligned views that feed matching are *not*
  a simple drop; they're tied to the vector store and need reconciliation with the unified
  `job` table + `country` column (see [§5](#5-open-decisions)) before anything is removed.
- **Ripple to update at Phase 3:** `serialize_job` (the DB-row→job mapper, per-country
  `config.COL`) and every blueprint query.

---

## 4. Track B (second) — Frontend rework

### 4.1 IC rebrand
**Status: IN PROGRESS (uncommitted on `develop`, 2026-06-29).** Independent of the DB work —
can land anytime. Applied to `frontend/static/css/{app.css, saved-dashboard.css, feedback.css}`
via a `:root` token set:

| Token | Value | Role |
|---|---|---|
| `--ic-blue` | `#24579B` | primary brand (was bright blue `#1a56c4`) |
| `--ic-blue-dark` | `#1C4680` | brand surfaces + hovers (was navy `#1a3864`) |
| `--ic-light-blue` | `#8EB4E3` | light accent (defined, lightly used) |
| `--ic-grey` | `#7F7F7F` | muted (defined) |
| `--ic-bg` | `#EDF1F8` | soft blue-tinted page/panel bg (replaced all warm cream tones) |
| `--ic-border` | `#E0E4EA` | cool borders (replaced warm greys) |
| `--ic-text` / `--ic-text-mid` | `#1A2332` / `#5A6677` | text |

Semantic colors (success green, error red, amber score/warning accents) were deliberately
preserved. Hover states were re-checked so no button has base == hover.
**To do:** commit; logo/assets TBD. (Backgrounds nudged a touch bluer per feedback —
`--ic-bg` `#F4F5F7` → `#EDF1F8`, kept restrained.)

### 4.2 Information architecture (from the client sketch)
The app is organised into two areas:
- **Tables** — the data/admin side: target companies, contacts, candidates, jobs, and
  user management. Admin-oriented.
- **Sales View** — the day-to-day working tool: the matching tool + filters, and the
  saved collections.

**The basics / home base = search + the saved trio + saved companies**
(`saved_job`, `saved_candidate`, `saved_contact`, `saved_company`). These are the core the
whole product is built around.

**Saved-job status pipeline.** Each saved job has a single-choice status, default `new`:

| Code (stored) | EN | DE |
|---|---|---|
| `new` | New | Neu |
| `in_progress` | In Progress | In Bearbeitung |
| `proposal_sent` | Proposal Sent | Angebot versendet |
| `won` | Won | Gewonnen |
| `lost` | Lost | Verloren |

Store only the canonical code; EN/DE are UI labels (i18n), not DB columns. This is a *sales*
pipeline, distinct from the saved-candidate *hiring* pipeline (Screening/Interviewing/etc.).

Tab visibility is gated by the access model ([§3.3](#33-access--collaboration-model)) — e.g.
the user-management tab is admin-only.

### 4.3 Expanded filters (jobs tab)
The job record carries ~28 fields (`serialize_job` in `services/search/utils.py`), but the
jobs tab today filters on only **state, occupation group, portal** (+ the keyword/candidate
input). Add filters drawn from columns that already exist:

- **First batch — do these first** (clean categorical dropdowns, low risk):
  `work_time` (full/part-time), `employment_relationship` (permanent/contract/temp),
  `education` (required level), `city` (finer than `state`).
- **Later** (need range UI / parsing / autocomplete): `salary` min–max (sparse/free-text →
  parse first), `posted` recency (last 7/30 days), `skills` keyword match (`skills`/`skills_en`),
  `company` (target_company) autocomplete, `municipality`.

Each new filter needs three changes: the filters endpoint to return its distinct values (today
it returns only states/occ_groups/portals), a control in the filter bar, and the query to apply
it. **Data caveat:** a filter is only as good as the column is populated — prioritise the
well-filled categorical columns; `salary` is sparse/free-text and needs parsing.

Candidate-search filters expand separately (dimensions TBD).

### 4.4 New tabs (depend on Track A)
- Target-companies & contacts views (browse, save).
- Saved-contacts and saved-companies collections (extend the existing Saved tab).
- User-management / access-control admin tab.

---

## 5. Open decisions
- **Rebrand:** logo / assets (TBD).
- **Filters:** confirm/trim the proposed job filter set ([§4.3](#43-expanded-filters-jobs-tab));
  pick candidate-search dimensions.

## 6. Decisions log
- 2026-06-29 — **Order: database first, then frontend** (build the backend structure before
  the UI that depends on it).
- 2026-06-29 — Country handling: **one set of tables + `country char(2)` column** (not
  per-country tables).
- 2026-06-29 — Tenant table named **`account_company`** (rejected `client_company` — collides
  with the recruiting sense of "client"; rejected bare `company` — ambiguous).
- 2026-06-29 — Data company named **`target_company`**.
- 2026-06-29 — User table named **`app_user`** (avoid MySQL reserved `user`).
- 2026-06-29 — Access model: `role` (admin/member) + `visibility` (own/all), scoped to
  `account_company` as a query rule.
- 2026-06-29 — **Dropped `user_visibility_grant` + the `selected` visibility level** (boss
  decision: users may simply see all other users — per-member control was unnecessary).
- 2026-06-29 — **Saved jobs/candidates/companies (+contacts) are visible only within the
  user's own `account_company`.** `all` = all colleagues in that company, never across
  companies. (Resolves the visibility-scope question.)
- 2026-06-29 — Saved jobs/candidates/contacts/companies are the product's home base, modelled
  as per-user junction tables.
- 2026-06-29 — IC palette tokenised in CSS ([§4.1](#41-ic-rebrand)).
- 2026-06-29 — Demo tab scope: of the borderline tabs, ship **only `company`**; defer `radar`,
  `analytics`, `guided`.
- 2026-06-29 — Rebrand: go **a bit bluer** but restrained — `--ic-bg` `#F4F5F7` → `#EDF1F8`.
- 2026-06-29 — Filters: prioritise **more filters on jobs** (plus candidates).
- 2026-06-29 — Per-country `View_Jobs_*` reconciliation is **low priority** (country view not
  important right now).
- 2026-06-29 — `saved_job.status` = single-choice sales pipeline
  `new | in_progress | proposal_sent | won | lost`, default `new`; EN/DE labels in the UI
  (store the canonical code, not both languages).
- 2026-06-29 — **Candidate/contact ownership: two columns** — `account_company_id` (company-owned,
  the privacy boundary) **and** `owner_id`→`app_user` (the employee who added it). Jobs +
  `target_company` stay the shared catalogue. `own`/`all` visibility filters on `owner_id`.
- 2026-06-30 — DB audited: it's two-tier — market data in per-country DBs (Austria/Slovakia),
  app data in `Jobs_Intelligence_AI`. **Greenfield rebuild of the app DB only**; market DBs
  untouched. Backup taken at schema `Jobs_Intelligence_AI_prerework`.
- 2026-06-30 — **Table names:** `saved_candidates` (renamed from `candidate`) is the only **normal
  app-owned table** — the full candidate record (staff create it; carries `account_company_id` +
  `owner_id`). `saved_jobs` / `saved_companies` / `saved_contacts` are **thin junction/reference
  tables** to the market catalogue (no data copied). Jobs / companies / contacts live in the market
  DBs, referenced by id (no cross-DB FK).
- 2026-06-30 — `saved_jobs` is user-owned (`owner_id`) AND linked to a `saved_candidate`
  (`saved_candidate_id`) — "shortlisting a job for a candidate"; `status` = Won/Lost sales pipeline.
- 2026-06-30 — **Contacts are catalogue-saved** (`saved_contacts` → country-DB `contacts`); no
  hand-created `contact` table for now. **`saved_jobs.job_id` is `BIGINT`** (market id is `INT`).
- 2026-06-30 — Canonical DDL committed to `data/sql/app_schema_v2.sql` (supersedes `app_schema.sql`;
  not yet applied; backup in `Jobs_Intelligence_AI_prerework`).
- 2026-06-30 — `job_vs_sync`/`sk_job_vs_sync` (vector-store sync) **preserved**; old `sk_*` app
  tables, `candidate_company`, and the empty `company` table dropped/folded. Concrete DDL in §3.2.
