# API Reference

Base URL: `http://localhost:5000` (port = `FLASK_PORT`).

**Auth:** every route except `/login` and static files requires a logged-in session. An
unauthenticated request to any `/api/*` route (or a JSON request) returns `401
{ "ok": false, "error": "Unauthorized" }`; a browser request to an HTML route redirects to
`/login`. Log in via `POST /login` (form `username`/`password`); seed logins are
`admin`/`admin`, `Monika2`, `hr_manager`.

**Country:** the running process serves one country (Austria or Slovakia), fixed at startup by
`COUNTRY` / `--sk`. All market data reflects that country; saved data is tagged with it.

Most responses are `{ "ok": true, ... }` or `{ "ok": false, "error": "..." }` with a 4xx/5xx
status. Routes are grouped by blueprint below.

---

## App routes (`app.py`)

| Route | Method | Purpose |
|-------|--------|---------|
| `/login` | GET, POST | Login page / submit credentials |
| `/logout` | GET | Clear session |
| `/` | GET | The SPA shell (`index.html`) |
| `/debug/schema` | GET | `DESCRIBE` the active `read_view` — verify column names after a DB change |

---

## Search — `search` blueprint (`/api`)

### POST `/api/match`
Runs AI vector matching for a candidate profile.

**Request:** `{ candidate_text, filters?, top_n?, max_results? }` — `candidate_text` required;
`filters` may contain `state`, `city`, `keywords`, `portal` (and `occ_group` for Austria);
`top_n` folds in as a result `limit`; `max_results` widens Stage-1 retrieval (capped at 50, used
by "find more jobs").

**Response:** `{ ok, count, jobs: [ { job_id, title, company, state, city, salary, url, portal,
occ_group, posted, score, score_pct, grade, match_reason, ... } ] }`.

**Pipeline:** OpenAI Responses API + `file_search` on the country's vector store → job ids →
resolved against the market DB (`Profile.read_view`) → hard filters → sorted by score.
**Fallback:** with no OpenAI key, keyword similarity against MySQL.

### Other search routes
| Route | Method | Purpose |
|-------|--------|---------|
| `/api/filters` | GET | Distinct dropdown values `{ states, occ_groups, portals, work_time, employment_relationship, education }` for the filter bar |
| `/api/match/stream` | POST | Streaming (SSE) variant of `/api/match` — emits `cycle` progress then a `done` event |
| `/api/match/rescore` | POST | Re-score a frozen result set against edited candidate text |
| `/api/quality` | POST | Match-quality scoring |

---

## Company — `company` blueprint (`/api`)

### GET `/api/company/id`
Lightweight companion to `/api/company` — resolves **only** the market company id (no jobs
fan-out, no LLM), so the company panel's Save button can enable immediately.

**Query:** `name` (company crawler name). **Response:** `{ ok, company_id }` (`company_id` is
`null` if none resolves — see [DATABASE.md](../infra/DATABASE.md) company-identity tiers).

### GET `/api/company`
Full company hiring profile.

**Query:** `name`. **Response:** `{ ok, company, company_id, contacts: [ { contact_id, name,
email, phone, linkedin } ], total_jobs, salary_stats, locations, states, top_titles, top_occ,
portals, date_range, work_types, recent_jobs, summary }`. `summary` is an AI hiring-profile blurb
(`services/reporting.summarize_company`) — the slow part of this call; it degrades to `""` on
error. `company_id` / `contacts` are best-effort (empty if the market DB lacks the source).

### POST `/api/jobs/contacts`
Batch-load contacts for job rows in search results.

**Request:** `{ job_ids: [..] }`. **Response:** `{ ok, contacts: { "<job_id>": [ { contact_id,
name, email, phone, linkedin } ] } }`.

### GET `/api/contact/jobs`
The active jobs a contact is linked to (drives the **Jobs** section of the saved-contact detail modal).

**Query:** `contact_id`. **Response:** `{ ok, jobs: [ { job_id, title, company, city, state, salary,
portal, posted, url, occ_group } ] }`. Read from `View_Jobs_Contacts` joined to `View_Jobs_Full`,
with a base-junction-table fallback (Slovakia); returns `{ jobs: [] }` if neither path exists.

### GET `/api/salary_stats`
Salary distribution for an occupational group.

**Query:** `occ_group`. **Response:** `{ ok, count, salaries: [...], mean, median }`. Excludes
`< €200`, trims the top 2%. Returns `{ count: 0, salaries: [] }` if no data.

### GET `/api/market/companies`
Browse the market catalogue's actively-hiring companies by name — independent of a job search.
Backs the Saved tab's Companies "Browse market" mode.

**Query:** `q` (optional name substring; empty returns the top companies overall).
**Response:** `{ ok, companies: [ { company_id, name, job_count } ] }`, ranked by open-job count,
max 20. Austria queries `companies` + `jobs.company_id`; Slovakia (no `companies` table) falls
back to `jobs.company_crawler_name` + `jobs.companies_finstat_id`.

### GET `/api/market/contacts`
Name search across the market catalogue's contacts — independent of a job/company lookup. Backs
the Saved tab's Contacts "Browse market" mode.

**Query:** `q` (required, 2+ chars). **Response:** `{ ok, contacts: [ { contact_id, name, email,
phone, company } ] }`, max 20. `company` is best-effort — one of the contact's linked jobs.

---

## Saved — `saved` blueprint (`/api/saved`)

Everything here is scoped to the caller's `account_company` with `own`/`all` visibility. Backed by
`services/candidate/store.py`.

### Saved jobs (for a candidate)
| Route | Method | Purpose |
|-------|--------|---------|
| `/api/saved` | GET | List saved jobs → `{ ok, count, jobs }` |
| `/api/saved` | POST | Add a job: `{ job, status?, extras?, candidate_profile? }` (dup → `message: "Already saved"`) |
| `/api/saved/<job_id>` | PATCH | Edit `{ pipeline_status?, notes?, grade?, extras?, + snapshot fields: title, company, location, salary, url, portal, posted }` (inline Saved-tab editing) |

### Saved candidates
| Route | Method | Purpose |
|-------|--------|---------|
| `/api/saved/candidate` | POST | Save a candidate (profile record). Company-wide name dedup → `{ already_saved, owner }` |
| `/api/saved/candidate/<name>` | PATCH | Edit candidate fields (title, seniority, status, location, contacts, languages, salary, availability, summary, skills) |
| `/api/saved/candidate/<name>` | DELETE | GDPR erasure — remove a candidate + their saved jobs (cascade) |
| `/api/saved/candidates` | GET | List saved candidates (drives the switcher + table; includes `createdBy` = who saved it) |
| `/api/saved/lookup` | GET | `?name=` or `?linkedin=` → `{ exists, candidate? }` |
| `/api/saved/load` | GET | `?name=` → `{ profile, jobs }` for one candidate (powers the detail modal) |
| `/api/saved/insights` | GET | Aggregate insights over saved data |

### Saved companies / contacts
| Route | Method | Purpose |
|-------|--------|---------|
| `/api/saved/companies` | GET | List bookmarked target companies |
| `/api/saved/companies` | POST | `{ target_company_id, snapshot?, notes? }` → `{ ok, added, companies }` (`added:false` = already saved) |
| `/api/saved/companies/<id>` | PATCH | Edit a saved company's fields (name, industry, location, notes) |
| `/api/saved/companies/<id>` | DELETE | Remove a saved company |
| `/api/saved/contacts` | GET | List bookmarked contacts |
| `/api/saved/contacts` | POST | `{ contact_id, snapshot?, notes? }` → `{ ok, added, contacts }` |
| `/api/saved/contacts/<id>` | PATCH | Edit a saved contact's fields (name, title, company, email, notes) |
| `/api/saved/contacts/<id>` | DELETE | Remove a saved contact |

---

## Candidate input — `candidate` blueprint (`/api/candidate`)

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/candidate/example-pdf`, `-2`, `-sk` | GET | Sample candidate CV PDFs for the demo |
| `/api/candidate/parse-pdf` | POST | Extract text from an uploaded CV PDF |
| `/api/candidate/parse-profile` | POST | Structured candidate profile from raw CV text |
| `/api/candidate/enrich-linkedin` | POST | AI-normalize a raw LinkedIn scrape |

---

## Job detail — `job_detail` blueprint (`/api`)

`/api/job_chat` (+ `/job_chat/reset`), `/api/desc_translate`, `/api/desc_compact`,
`/api/desc_cv_questions`, `/api/desc_outreach`, `/api/candidate_strength` — all POST. Per-job
detail-modal helpers: chat about a posting, translate/compact the description, generate CV
questions / outreach, and score candidate strength against the job.

---

## Other blueprints

| Blueprint | Prefix | Routes |
|-----------|--------|--------|
| `interview` | `/api/interview` | `/questions`, `/extract`, `/parse`, `/analyze`, `/context`, `/followup`, `/summarize`, `/model_answer`, `/opportunities`, `/assess` |
| `feedback` | `/api/feedback` | `POST` (submit) / `GET` (list) in-app feedback |

> The `guided` and `cluster` blueprints were removed from `master` on 2026-07-02 (the code
> lives on `develop`). See [planning/FRONTEND_DB_REWORK_PLAN.md](../planning/FRONTEND_DB_REWORK_PLAN.md).
