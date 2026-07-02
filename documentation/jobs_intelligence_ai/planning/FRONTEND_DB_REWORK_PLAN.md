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

### 4.2 Information architecture (simplified — confirmed 2026-06-30)
Collapse the current many-tab UI (search/saved/radar/analytics/interview/clustering/guided/
company/map) down to **two top tabs**. **On `master` these are the only two tabs** — the
experimental ones (radar/analytics/interview/clustering/guided/map) fold away entirely, not
behind a toggle.

The two tabs are **deliberately different paradigms**, not one shared layout:

- **Search — conversational.** A free-text / chat-style way to look things up across the market:
  **jobs, companies, and contacts** (and candidates — see open point). You describe what you
  want, get results back, and save the ones worth keeping. This is the discovery/sourcing surface.
- **Saved — the database view.** A browsable, table/grid-style view of the shared `saved_*`
  collections (jobs / companies / candidates / contacts). This is where the *volume* of data lives,
  so it must read like a database — sortable, scannable, filterable rows. Company-scoped + own/all
  visibility → **this is the collaboration surface**; everyone in the company works off the same
  saved data.

This maps 1:1 onto the schema: search→save writes into `saved_*`; `account_company` + `visibility`
make the Saved view shared within the firm. The backend is already shaped for it — the remaining work
is the **frontend**: build the conversational search across the three entity types, build the
database-grid Saved view, and drop the experimental tabs on `master`.

**Home base = `saved_candidates` + `saved_jobs` + `saved_companies` + `saved_contacts`** — the core
the product is built around.

**Open point — "search candidates":** jobs/companies are market data (catalogue → save); candidates
aren't in a market catalogue — they're created (CV upload) or sourced (LinkedIn). So "search
candidates" = browse/search the company's own saved-candidate pool and/or source new ones to save.
Confirm which (likely both).

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

### 4.3 Expanded filters (jobs tab) — first batch DONE (2026-07-02)
The job record carries ~28 fields (`serialize_job` in `services/search/utils.py`); the jobs
tab now filters on **state, city, occupation group, portal, work_time, employment_relationship,
education** (+ keyword/candidate input).

- **First batch — DONE:** `work_time` (full/part-time), `employment_relationship`
  (permanent/contract/temp), `education` (required level). `city` turned out to already be a
  working free-text substring filter (`#filterCity` + `passes_filters`) predating this batch —
  no change needed there; a dropdown would in fact be wrong for it (1,721 distinct AT city
  values — see decisions log).
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
- ~~User-management / access-control admin tab~~ — **dropped 2026-07-02** (user decision):
  `app_user` rows are managed by hand directly in the `Jobs_Intelligence_AI` DB, not through
  an in-app screen. `create_user()` in `services/auth/accounts.py` stays as a DB-facing helper
  with no route/UI calling it.

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
  backup in `Jobs_Intelligence_AI_prerework`).
- 2026-06-30 — **Schema is APPLIED (live) and verified working end-to-end.** Tables were created
  incrementally (auth + store-rewrite work), not by running the DDL file — so the *live* tables are
  ahead of `app_schema_v2.sql` (extra columns: `snapshot`/`extras`, richer candidate fields;
  `saved_jobs.status` is VARCHAR). Seeded: `account_company` id=1 + 3 `app_user` logins. Smoke test
  confirmed save-company/save-contact (with snapshot) + own/all visibility. **Still pending: the
  cutover that DROPS the old tables** (candidate/sk_*/users/…; keep `job_vs_sync`/`sk_job_vs_sync`).
- 2026-06-30 — **Frontend IA simplified to TWO top tabs:** Search (searches jobs/companies/candidates)
  + Saved (the shared "database view" = the collaboration surface). Other tabs fold away/behind. Maps
  1:1 to `saved_*` + `account_company`/`visibility`. (Track B frontend work; backend already shaped.)
- 2026-06-30 — **The two tabs are different paradigms, not one shared layout:** Search is
  **conversational** (chat/free-text discovery across jobs + companies + contacts); Saved is a
  **database/grid view** (sortable, scannable rows — it holds the bulk of the data). On `master`
  these are the *only* two tabs; the experimental ones (radar/analytics/interview/clustering/guided/
  map) fold away entirely.
- 2026-06-30 — **Search scope widened: jobs + companies + contacts** (not jobs-only) — the
  conversational search spans all three market entity types.
- 2026-06-30 — Save-company + save-contact to be wired (new store fns + routes + buttons) alongside the
  saved-blueprints step; old work-history `/api/saved/companies` route retired (now empty).
- 2026-06-30 — `job_vs_sync`/`sk_job_vs_sync` (vector-store sync) **preserved**; old `sk_*` app
  tables, `candidate_company`, and the empty `company` table dropped/folded. Concrete DDL in §3.2.
- 2026-06-30 — **Saved tab now spans all four collections** (commit 7e9bd8e): added a collection
  switcher **Candidates | Jobs | Companies | Contacts**. (Superseded same day — see next entry.)
- 2026-06-30 — **Saved tab SIMPLIFIED (user directive):** dropped the dashboard, the match-insights /
  interview-notes panels, the Table/Dashboard + Database/Local + Candidates/Templates toggles, the
  "Save all to database" / "Load from database" buttons, candidate inline-edit + column chooser, and the
  Excel/PDF export — i.e. **all session/local staging**. The Saved tab is now just the four collection
  tabs, each a plain sortable DB grid (click-header sort, per-row Remove), auto-loaded. Rationale: saving
  already writes straight to the DB (saving a job persists the candidate+job), so local staging was
  redundant. `saved.js` rewritten ~1180→~190 lines; `_trackLocalCandidate` kept as a no-op stub for its
  candidate.js/guided.js callers. Candidate **status is now read-only** in this view (editing dropped —
  can be re-added later if needed). Verified in-browser.
- 2026-06-30 — **Search-side save wiring DONE** (verified in-browser): (1) **candidate auto-save** —
  a checkbox by "Run matching" (default on) persists the candidate to the DB on each run; toggle it off
  and a manual "Save candidate" button appears. (2) **company + contact save from the company panel** —
  clicking a company name opens the panel, which now shows a **Save company** button and a **Contacts**
  section (people linked to the company's jobs) each with a **Save** button. Backend: `/api/company`
  now returns `company_id` (market `companies.id`) + `contacts` (from `View_Jobs_Contacts`, guarded so a
  market DB lacking them just disables the buttons). Saves flow into `saved_candidates`/`saved_companies`/
  `saved_contacts` and show up in the Saved-tab collections. Jobs already had a save button (unchanged).
- 2026-06-30 — **Per-job contacts in search results + robust company save:** (1) each result row now
  shows a contact indicator in the company cell (name if one, "N contacts" if several) — batch-loaded
  after render via a new `POST /api/jobs/contacts` (from `View_Jobs_Contacts`); clicking opens a small
  panel (`#jcModal`) listing the contacts each with a Save button (reuses the `save-contact` action →
  `saved_contacts`). ~51k active jobs carry contacts. (2) The company panel's **Save company** button
  is now reliable — `company_id` falls back to `View_Jobs_Full.company_id` when the exact companies-table
  name lookup misses. Verified in-browser (endpoint, chip render, modal, save).
- 2026-06-30 — **Candidate dedup (company-wide):** saving a candidate whose NAME already exists in the
  account_company (saved by anyone) is blocked — `/api/saved/candidate` returns `already_saved:true` +
  the owner's name instead of upserting. The run-row shows a green "✓ Candidate saved" or a red
  "● <name> already saved by <owner>" indicator (both the auto-save and manual paths). `lookup_candidate`
  now also returns the owner (LEFT JOIN app_user). Verified in-browser (new→green, re-save→red).
- 2026-06-30 — **Piece #1 of the two-tab collapse DONE on `master`** (verified in-browser): removed the
  Candidate/Analytics mode-toggle and the radar/map/analytics-summary tabs+panels; deleted `radar.js`,
  `map.js`, `radar.py`, `analytics.py`; renamed the "Saved Jobs" tab to **"Saved"**. Guided + clustering
  are **folded away from the UI** (entry buttons removed) but their now-inert code (`guided.js`/
  `clustering.js` + `cluster.py`/`guided.py` + the `#zone-guided`/`#zone-multiple` markup) is **kept,
  to be deleted in Piece #3** (the conversational-search rebuild) since it's coupled to `candidate.js`'s
  input orchestration. Remaining: Piece #2 (Saved → grid view), Piece #3 (conversational Search across
  jobs/companies/contacts).
- 2026-07-01 — **Save-company works for Slovakia + button available immediately (verified in-browser).**
  Two problems fixed in `blueprints/company.py` + the company panel:
  (1) **SK never showed the Save button.** The `company_id` resolver only tried `companies.id` and
  `View_Jobs_Full.company_id` — Slovakia's market DB has *neither* table/column, and each failed lookup
  threw an exception that aborted the whole `try` block (silently killing the **Contacts** query too).
  Fix: the 3-tier resolver is extracted to `_resolve_company_id(conn, name)` with **each attempt isolated
  in its own try/except**, plus a **third SK-specific tier** reading `jobs.companies_finstat_id`
  (FK → `companies_finstat.id`) directly from the base `jobs` table — fast, and it covers ~99.7% of active
  SK jobs (the slow `View_Jobs_Full` fan-out is avoided). Contacts get the same treatment: when
  `View_Jobs_Contacts` is absent (SK), they fall back to the base `contact_jobs_junction` + `contacts` +
  `jobs` tables. So `/api/company` now returns a real `company_id` + `contacts` on both markets (AT
  unchanged — verified no regression).
  (2) **Button waited for the slow profile load.** The Save button used to render inside `/api/company`'s
  response, which includes the LLM `summarize_company` call (~25–30 s), so it only appeared once everything
  finished. It's now a **persistent button in the modal header** (`#coSaveBtn`, `templates/index.html`),
  shown the moment the panel opens; a new **lightweight `GET /api/company/id?name=`** (id resolution only,
  no jobs fan-out, no LLM — ~250 ms) runs in the background to enable it while the full profile still loads.
  `candidate.js`: `_prepCompanySaveBtn()` reveals + enables the header button; the old in-body `.co-save-row`
  block (and its CSS) is removed. Verified in-browser (SK "Swiss Re"): button usable at ~1.2 s while the body
  still shows the spinner, `company_id` 47980 + 13 contacts resolve, save → `saved_companies`.
- 2026-07-01 — **Saved → Candidates: owner column, seniority fix, edit, detail modal (verified in-browser).**
  Four changes to the candidates collection:
  (1) **"Saved by" column.** `list_candidates_detailed` now `LEFT JOIN app_user` and returns
  `createdBy` = `COALESCE(display_name, username)` (was hardcoded `""`); a "Saved by" column shows who
  originally saved each candidate.
  (2) **Seniority was always blank for CV candidates.** Root cause: the CV-text parser schema
  `CandidateProfile` (`services/candidate/config.py`) had no `seniority` field, so only LinkedIn imports
  (whose `LinkedInProfile` has it) ever got one. Added `seniority` to the schema + parse prompt; the DB
  column and grid column already existed. (Pre-existing rows stay blank until re-parsed or edited.)
  (3) **Editable details.** `seniority` added to the editable field sets (`store._EDITABLE_FIELDS` +
  `saved.py::_CANDIDATE_EDIT_FIELDS`); the `PATCH /api/saved/candidate/<name>` route already existed.
  (4) **Candidate detail modal.** Clicking a name in the grid opens `#candModal` (large modal, like the
  company panel) via `candidate.js::openCandidateDetail(name, row)` — the grid row fills the header
  instantly, `GET /api/saved/load?name=` fetches the full parsed profile (skills, experience, education,
  certifications, contacts, summary) + the candidate's **saved matched jobs**. An inline **Edit** mode
  turns the key fields into a form and PATCHes on save, then refreshes the grid. Verified in-browser (SK):
  Saved-by shows "Administrator", name opens the modal with profile + 1 matched job, editing seniority
  persists and reflects in the grid. Also fixed a latent bug — there was no global `.hidden{display:none}`,
  so header Save buttons relied on a class that didn't hide; added a scoped `.co-modal-save.hidden` rule
  (also hardens the company Save button's no-id case).
- 2026-07-02 — **Saved-job pipeline status is now editable in the Saved grid (verified in-browser).**
  The Status cell in the Jobs collection is an always-live dropdown (no row-Edit needed) over the
  canonical sales pipeline `new | in_progress | proposal_sent | won | lost`; changing it PATCHes
  immediately, tinted per stage. Codes are now stored canonically end-to-end: the job-detail modal's
  initial-status select (`#modalStatusSel`) sends codes instead of the old `New/Contacted/Placed/
  Rejected` labels, and the saved blueprint **validates** the code on POST + PATCH (400 otherwise).
  Dead dashboard leftovers `updateStatus`/`updateNotes`/`removeJob` removed from `modal.js`.
  (`saved_jobs` was empty, so no legacy-value migration was needed.)
- 2026-07-02 — **Conversational search (Piece #3) moves to `develop`, not `master`.** The
  chat-style search across jobs/companies/contacts is the risky unbuilt part; it will be built and
  hardened on `develop` and promoted only when it's trustworthy. `master` keeps the current
  structured search (candidate input + filters). The inert `guided.js`/`clustering.js` code kept
  for Piece #3 stays parked on `master` until that work lands on `develop`.
- 2026-07-02 — **SK descriptions exist — the app just doesn't read them.** ~45% of active SK jobs
  (19.6k / 43.6k) have a scraped `description` via `description_jobs_junction` + `descriptions`;
  the RAG pipeline embeds them from `View_Jobs_Descriptions`. That view is too slow to scan
  (window fn + GROUP BYs — COUNT(*) times out), but per-id lookups on the base tables are fast
  (~60 ms/10 ids). Planned fix: per-id description fetch in the SK job-detail path, keep
  `View_Jobs_Full` as the read view.
- 2026-07-02 — **SK descriptions FIX SHIPPED (verified live, both markets).** New optional
  `Profile.desc_lookup_sql` hook (SK-only; AT stays None): the job-fetch paths in
  `infra/database.py` batch-fetch scraped descriptions per id via
  `_add_scraped_descriptions()` → row key `_scraped_description`, and `serialize_job`
  prefers it over `COL['description']` (which stays mapped to `summary` as the fallback for
  the ~55% of SK jobs without one). Verified: SK jobs with junction rows serialize the full
  scraped text, jobs without fall back to summary, AT unchanged; fetch+enrich ~100 ms/3 ids.
- 2026-07-02 — **TRACK A CUTOVER COMPLETE — old tables DROPPED.** All 13 legacy tables
  (`candidate`, `sk_candidate`, `candidate_saved_job`, `sk_candidate_saved_job`,
  `candidate_company`, `sk_candidate_company`, `company`, `sk_company`, `target_candidate`,
  `sk_target_candidate`, `users`, `sk_feedback`, `sk_audit_log`) checksum-verified identical to
  the `Jobs_Intelligence_AI_prerework` backup, then dropped (junctions before parents; no FK from
  any kept table). 10 tables remain: account_company, app_user, saved_* ×4, audit_log, feedback,
  job_vs_sync, sk_job_vs_sync. Pre-drop code fixes: the feedback blueprint now writes the unified
  `feedback` table with account/user attribution (was `{prefix}feedback` → `sk_feedback` on SK);
  `target_candidate` dropped per the TBD (guided doesn't ship on `master`; its `save_target`/
  `list_targets` store fns go with the guided removal). `app_schema_v2.sql` regenerated from
  SHOW CREATE TABLE — now a byte-for-byte mirror of live. Verified: app boots, login + feedback +
  saved endpoints exercised, full suite green (185 tests incl. e2e).
- 2026-07-02 — **Guided/clustering: keep on `develop`, remove from `master`** (user decision).
  Not a hard delete — `develop` gets `master` merged in (so it stays current AND keeps the
  guided/clustering code); `master` then drops guided.js/clustering.js/guided.py/cluster.py,
  their zone markup and candidate.js/boot.js hooks. Piece #3 (conversational search) is built
  on `develop` and promoted when trustworthy.
- 2026-07-02 — **Guided/clustering removal from `master` EXECUTED** (verified: full suite green
  incl. the real-browser e2e tabs smoke; live preview clean, no console errors). `develop` was
  fast-forwarded to `master` first (it had no unique commits), so it retains everything.
  Removed from `master`: `guided.js`, `clustering.js`, `blueprints/guided.py`,
  `blueprints/cluster.py`, `services/clustering/`, `shared/taxonomy.py` (orphaned), the
  `#zone-guided`/`#zone-multiple`/`#segModal`/`#backToSegments`/`#gbSaveTemplateBtn` markup, the
  single↔multiple workflow plumbing in `candidate.js` (`setWorkflow`/`_applyChrome`), the guided
  branch of `buildCandidateText`, `store.save_target`/`list_targets` (+ `_T_TARGET`), the
  clustering + taxonomy test suites, and the unused `has_guided`/`has_map`/`has_analytics`
  template context vars. KEPT on `master`: the profile feature flags (config-level; geo/reporting
  read `HAS_MAP`) and `services/candidate/guided_builder.py` (self-contained, covered by unit +
  smoke tests — removable later if wanted). Dead gb-*/mc-*/seg CSS left in `app.css` for now.
- 2026-07-02 — **Candidate-assistant chat also removed from `master`, kept on `develop`**
  (user decision, same pattern as guided/clustering). Unlike guided/clustering this was a
  *live* feature (not dead/folded-away code), so the removal was scoped carefully to avoid
  touching the unrelated per-row freeze/pin feature and the `/api/match/rescore` re-score
  flow, which share `search.js`/`state.js` with the assistant's highlight overlay but are
  core search features, not assistant-only. No branch merge/fast-forward was needed —
  `develop` already had the code untouched (it only lacks the *previous* guided/clustering
  removal commit, by design).
  Removed from `master`: `assistant.js` (whole file) + its docked-chat markup block in
  `index.html` + its `.cand-asst-*`/`.chat-*`/`.hl-*` CSS in `app.css`; the boot.js import;
  `services/candidate/assistant.py` (+ `ASSISTANT_PROMPT`/`LANG_INSTRUCTIONS`/`CandidateReply`/
  `ProfileUpdates` from `services/candidate/config.py`); `services/enrichment/highlighter.py`
  (+ `HIGHLIGHT_PROMPT`/`HighlightResult` from its config); `services/search/match_analysis.py`
  (+ `ANALYZE_MODEL`/`ANALYZE_PROMPT`/`MatchAnalysis` from its config);
  `Orchestrator.match_url` + `JobSearch.fetch_by_url` + `infra.database.fetch_jobs_by_url`
  (the URL-match flow, assistant-only, no other caller); the `/api/candidate/assistant`,
  `/api/candidate/assistant/reset`, `/api/match/url`, `/api/match/highlight`,
  `/api/match/analyze` routes; the `highlightedJobIds`/`highlightCriterion`/`candAsstNotes`/
  `SESSION_ID` state fields and their reset/render hooks in `search.js`/`candidate.js`
  (`_withAsstNotes` deleted); 5 dedicated test files plus surgical trims to 2 mixed test files
  (`test_candidate_smoke.py`, `test_2_converted_routes.py`). KEPT (confirmed unrelated):
  `pinnedJobIds`/freeze-a-row, `/api/match/rescore`, `services/enrichment/observation.py`
  (a different Saved-tab chat feature). Verified: full suite green (169 tests, including
  live smoke), live preview clean.
- 2026-07-02 — **Search-tab candidate-DB usability fixes (verified in-browser).** (1)
  `#btnSaveCandidate` ("＋ Save candidate") is now **always visible** — it used to be
  `display:none` and only revealed when the "Auto-save candidate" checkbox was unchecked,
  which read as a missing button. The checkbox still controls auto-save-on-run; the button
  is now a persistent explicit-save affordance regardless of that setting (dead
  `toggle-autosave-candidate` action removed). Clicking it with no profile loaded now shows
  "Add a candidate profile first" instead of silently no-op'ing. (2) **New "Search saved
  candidates" box** next to "Example candidates" (`candidate.js`): type-ahead over
  `GET /api/saved/candidates`, filtered client-side by name substring, refetched fresh each
  search session; picking a result loads the full profile + saved jobs via the existing
  `GET /api/saved/load?name=` path. Refactored `loadCandidateFromDb`'s fetch+render logic
  into a shared `_loadSavedCandidate(name)` so the duplicate-warning banner's "Load saved
  records" button and the new search box share one code path. Reuses the `.ex-dropdown-*`
  CSS classes from the Example-candidates dropdown (only the input-vs-button trigger needed
  new styling: `.db-search-*`). No new backend routes — both fixes are frontend-only.
- 2026-07-02 — **§4.3 first-batch job filters SHIPPED (verified live, both markets).**
  `work_time`, `employment_relationship`, `education` are now filter-bar dropdowns, backed by
  new per-country SQL in `config/profiles.py::_AT_FILTER_QUERIES`/`_SK_FILTER_QUERIES`
  (`GET /api/filters` → `infra.database.get_filter_options()`, already generic over whatever
  keys `Profile.filter_queries` defines — no endpoint code changed) and a matching exact-match
  check added to `services/search/utils.py::passes_filters()`. **Live-data finding:** AT's
  `work_time`/`employment_relationship`/`education` are messy AMS free-text columns that often
  store a comma-joined combination (e.g. "Lehre/Lehre mit Meisterprüfung, Matura") — raw
  distinct counts are 51/468/1088, so all three AT queries use the same frequency-cut shape as
  the existing `occ_groups` query (`HAVING COUNT(*) >= 20`), landing on ~10–35 dropdown options
  each. SK's equivalents (`work_time`/`contract_type`/`education`) are a clean 3–22-value
  taxonomy — the same query shape is a no-op there but keeps both profiles structurally
  identical. `employment_relationship` maps to the `contract_type` column on SK (see `_SK_COL`).
  **`city` needed no work** — investigation found it's already a working free-text substring
  filter (predates this batch); confirmed via live query that AT alone has 1,721 distinct city
  values, so a dropdown would have been the wrong UI for it anyway. Frontend: 3 new `<select>`s
  added to the filter bar (wraps to a second grid row under the existing 5-column
  `.filter-row` grid — no CSS changes needed); `search.js::loadFilters()` populates them;
  extracted a shared `_readFilterInputs()` helper (was duplicated verbatim in `runMatching()`
  and `findMoreJobs()`) so filters are read from the DOM in one place. Verified: dropdowns
  populate with real AT data live, selecting a `work_time` value narrows a 21-job candidate
  set down to the 1 matching job end-to-end; full suite green (147 non-smoke tests).
- 2026-07-02 — **User-management admin tab DROPPED from §4.4** (user decision). `app_user`
  accounts are provisioned by hand directly against the `Jobs_Intelligence_AI` DB — no in-app
  add-user screen. Remaining §4.4 scope: target-companies/contacts browse view only.
