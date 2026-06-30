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

### 3.2 Target schema (the ERD)
Single set of tables; **`country char(2)` column** instead of per-country tables.

**Accounts & access**
- `account_company` — the tenant (the firm whose staff log in). `id, name, created_at`.
- `app_user` — a person who logs in; belongs to an `account_company`.
  `id, account_company_id→account_company, name, email, password_hash, role, visibility`.
  (Named `app_user`, not `user`, to avoid the MySQL reserved word / system table.)
- `audit_log` — `id, user_id→app_user, action, entity_type, entity_id, created_at`.

**Data — the searchable universe**
- `target_company` — a company you recruit for / save. `id, name, country, industry, …`.
- `job` — `id, target_company_id→target_company, title, country, description, …`.
- `candidate` — `id, name, country, profile, …`.
- `contact` — a person at a target company. `id, target_company_id→target_company, name, email`.

**Saved — the home base (junction tables, per user)**
- `saved_job` — `id, user_id→app_user, job_id→job, status, saved_at`. `status` =
  `new | in_progress | proposal_sent | won | lost` (default `new`; see §4.2 for EN/DE labels).
- `saved_candidate` — `id, user_id→app_user, candidate_id→candidate, saved_at`.
- `saved_contact` — `id, user_id→app_user, contact_id→contact, saved_at`.
- `saved_company` — `id, user_id→app_user, target_company_id→target_company, saved_at`.
- Each saved table gets `unique(user_id, item_id)`.

```
account_company
   └─1:N─ app_user    (role: admin | member,  visibility: own | all)
             ├─1:N─ saved_job        ─N:1─▶ job
             ├─1:N─ saved_candidate  ─N:1─▶ candidate
             ├─1:N─ saved_contact    ─N:1─▶ contact
             ├─1:N─ saved_company    ─N:1─▶ target_company
             └─1:N─ audit_log

target_company
   ├─1:N─ job        (FK target_company_id)
   └─1:N─ contact    (FK target_company_id)

candidate           standalone — shared pool, no FK

Every data table (job, candidate, target_company, contact) carries a `country` column.
Each saved_* table is a per-user junction: (user_id, item_id) with unique(user_id, item_id).
```

### 3.3 Access & collaboration model
The tool promotes collaboration: by default users see every other user's saved data. The
fine-grained per-member grant was dropped as unnecessary (boss decision, 2026-06-29).

- `app_user.role`: `admin | member`.
- `app_user.visibility`: `own | all`.
  - `all` (default) — own + every other user's data **within the same `account_company`**.
  - `own` — only their own records (an opt-out switch if a user shouldn't see others).
- **The company boundary is always enforced.** A user only ever sees saved jobs / candidates /
  companies (and contacts) belonging to users in their own `account_company` — never another
  company's. `all` vs `own` only widens/narrows visibility *within* that boundary.
- **Scoping is a query rule, not a column on the data tables.** It resolves by joining each
  `saved_*` row through its owning `app_user` and filtering to the viewer's `account_company`
  (+ visibility). Jobs stay a shared catalogue; what's company-private is *who saved what*.

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

### 4.3 Expanded filters
Add more filter dimensions — **primarily on jobs** (the main ask) and also candidate search.
Exact dimensions TBD.

### 4.4 New tabs (depend on Track A)
- Target-companies & contacts views (browse, save).
- Saved-contacts and saved-companies collections (extend the existing Saved tab).
- User-management / access-control admin tab.

---

## 5. Open decisions
- **Candidates/contacts ownership — confirm.** Recommendation: give `candidate` and `contact`
  an `account_company_id` so each is **owned by the company that created it** — your staff's
  private pool (all employees of that company see it; other companies never do). Jobs +
  `target_company` stay the shared market catalogue; `saved_*` remain per-user shortlists within
  the company. (Alternative: fully shared records scoped only via `saved_*` — simpler, but no
  company-owned pool.) **Awaiting confirm.**
- **Rebrand:** logo / assets (TBD).
- **Filters:** exact new job (and candidate) filter dimensions (TBD).

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
