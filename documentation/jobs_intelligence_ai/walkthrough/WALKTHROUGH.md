# Quick Walkthrough

A guided tour for someone new to this codebase: what the project is, how the folders fit
together, and how a request travels from the browser down to MySQL/OpenAI and back. For the
exhaustive reference docs, see the links at the bottom — this page is the map, not the atlas.

---

## 1. What this app does

A Flask web app for a recruitment agency (Acme Recruitment). A staff member enters a
candidate profile (CV upload, free text, or LinkedIn import); the app searches a live market
database of job postings and returns ranked matches. Staff **save** the things worth keeping —
candidates, jobs, companies, contacts — into a shared, company-scoped database the rest of their
team also reads from.

The same code serves two countries (Austria, Slovakia), picked at startup — see [§6](#6-one-codebase-two-countries).

---

## 2. Run it locally

```bash
pip install -e .
cp .env.example .env             # fill in OPENAI_API_KEY and DATABASE_URL[_SK]
python -m jobs_intelligence_ai            # Austria (default)
python -m jobs_intelligence_ai --sk       # Slovakia
```

Open `http://localhost:5000`, log in with `admin` / `admin`. `http://localhost:5000/debug/schema`
dumps the active market view's columns — useful after any DB change.

`python -m jobs_intelligence_ai` runs [`__main__.py`](../../../src/jobs_intelligence_ai/__main__.py),
which calls `main()` in [`frontend/app.py`](../../../src/jobs_intelligence_ai/frontend/app.py) —
that's the whole entry point, no WSGI server or separate process to start.

---

## 3. Project structure, top to bottom

```
src/jobs_intelligence_ai/
├── __main__.py          entry point: python -m jobs_intelligence_ai [--sk|--at]
├── config/              settings.py + profiles.py — see §6
├── frontend/            the Flask app itself
│   ├── app.py           create_app(): session auth, /login, /, /debug/schema
│   ├── blueprints/      one file per route group (search, saved, company, candidate,
│   │                    job_detail, interview, feedback) — thin: parse request → call
│   │                    a service → jsonify the result
│   ├── templates/       index.html (SPA shell), login.html
│   └── static/
│       ├── js/          ES modules, no build step — boot.js is the entry point
│       └── css/         app.css (IC brand palette)
├── infra/
│   └── database.py      SQLAlchemy engine(s) + query helpers
├── services/             the actual business logic, one package per concern:
│   ├── search/          candidate → ranked jobs (the core matching pipeline)
│   ├── candidate/        persistence (store.py) + CV/LinkedIn parsing
│   ├── enrichment/       post-retrieval re-scoring, seniority, quality
│   ├── reporting/        AI company-profile summaries, PDF/briefing reports
│   ├── interview/        live interview scoring
│   ├── clustering/       CV → talent segments (develop branch only, see below)
│   ├── geo/              Austria Bundesland polygon data
│   ├── stats/            salary distribution charts
│   └── auth/             MySQL-backed login
└── shared/               cross-service helpers (llm.py = the one OpenAI client, grading.py)
```

Two things worth internalizing early:

- **Blueprints are thin.** Open any file in `frontend/blueprints/` and you'll see `request.get_json()`
  → one call into `services/...` → `jsonify(...)`. All the actual logic (matching, scoring, DB
  queries, LLM prompts) lives in `services/`, not in the route handlers.
- **The frontend has no build step.** There's no webpack/vite/React — `static/js/*.js` are native
  ES modules the browser imports directly, wired together via a shared `app` object
  (`state.js`) and a delegated `data-action` click dispatcher (`boot.js`). See
  [FRONTEND.md](../frontend/FRONTEND.md) for the full module map.

> Note: a "Multiple CVs" clustering mode and a guided-candidate-builder chat exist in the code
> but were removed from `master` on 2026-07-02 (they live on `develop`). Don't be surprised if
> you don't find `guided`/`cluster` blueprints on this branch.

---

## 4. Every service is runnable standalone

Each package under `services/` has a `__main__.py`, so you can exercise it from the command line
without going through Flask/the browser at all — handy for poking at one piece in isolation, or for
confirming a DB/API-key problem is in the service layer rather than the web layer. All of them
apply `--country`/`-c` the same way the app's own `--sk` flag does (env var set before any
config-bound import), and print human-readable output rather than raw model JSON.

| Command | What it does |
|---|---|
| `python -m jobs_intelligence_ai.services.search "<candidate text>"` | Run the full matching pipeline (§5), print ranked jobs |
| `python -m jobs_intelligence_ai.services.stats` | Print the pure job-quality signals for a bundled sample job (offline) |
| `python -m jobs_intelligence_ai.services.candidate "<CV text>"` | Parse a structured candidate profile (live OpenAI call) |
| `python -m jobs_intelligence_ai.services.auth <user> <pass>` | Verify a login against the app DB (`--list` to dump all users) |
| `python -m jobs_intelligence_ai.services.enrichment <job_id> [...]` | Fetch real job(s) by id, print seniority + quality classification |
| `python -m jobs_intelligence_ai.services.interview <job_id> --candidate-text "..."` | Fetch a real job by id, generate interview questions against a CV |
| `python -m jobs_intelligence_ai.services.job_detail <job_id> --op compact` | Run one Job Detail tool (`translate`/`compact`/`cv-questions`/`outreach`/`strength`) on a real job |
| `python -m jobs_intelligence_ai.services.reporting "<company name>"` | Fetch a real company's postings by name, print the AI hiring-profile summary |
| `python -m jobs_intelligence_ai.services.geo` | Print the bundled Austria Bundesland polygon summary (pure data, no DB/LLM) |

`search`/`stats` take a single plain-text argument, so their CLI is just that text (or, for
`stats`, a bundled offline sample — no DB needed). The rest operate on richer objects (a job row, a
company's aggregated stats), so their CLI fetches that object for real — by job id or company name
— rather than faking one up, using the same DB helpers (`JobSearch.fetch`, `fetch_jobs_by_ids`) the
web routes use. `clustering` has no `__main__.py` — it isn't on `master` (see the note in [§3](#3-project-structure-top-to-bottom)).

---

## 5. How the pieces connect — one request, end to end

The clearest way to see "how the Python connects to the app" is to trace the single most
important call: a candidate search. Every other feature (save a job, open a company panel, chat
about a job) follows the same shape.

```
Browser                          Flask (Python)                        External
────────────────────────────────────────────────────────────────────────────────
search.js: runMatching()
  api.post('/api/match', {           <- fetch() over HTTP, JSON body
    candidate_text, filters, top_n
  })
                              ──►  blueprints/search.py: api_match()
                                     • parses request body
                                     • calls Orchestrator.run(...)
                                                  │
                                                  ▼
                                     services/search/orchestrator.py
                                       Stage 1 — Retrieve:
                                         EmbeddingSearch.search_scored()  ──► OpenAI
                                                                              vector_stores.search
                                                                              (file_search over the
                                                                              country's vector store)
                                         → a set of job ids
                                       Stage 2 — Grade:
                                         JobSearch.fetch(ids, filters)   ──► MySQL
                                                                              (Profile.read_view,
                                                                              e.g. View_Jobs_Full)
                                         Grader.grade(candidate_text,
                                                      candidates)        ──► OpenAI
                                                                              responses.parse()
                                                                              (Structured Outputs)
                                         → ranked jobs with score/grade
                                     ◄── jsonify({ ok: true, jobs: [...] })
search.js: renders the
results table from
data.jobs
```

Concretely, in code:

1. **Frontend fires the request.** [`search.js:393`](../../../src/jobs_intelligence_ai/frontend/static/js/search.js)
   — `await api.post('/api/match', { candidate_text: text, filters, top_n: topN })`. `api.post` is
   a ~5-line wrapper in [`api.js`](../../../src/jobs_intelligence_ai/frontend/static/js/api.js) around
   `fetch()` that unwraps the `{ ok, ... }` envelope and throws on `ok: false` — every module in
   `static/js/` calls the backend through this one file, never raw `fetch()`.

2. **Flask routes it.** [`blueprints/search.py:52`](../../../src/jobs_intelligence_ai/frontend/blueprints/search.py)
   — `@bp.route("/match", methods=["POST"]) def api_match()`. It does almost nothing itself: reads
   `candidate_text` off the JSON body, builds a `filters` dict, and calls
   `_orchestrator.run(candidate_text, filters, max_results=...)`. `_orchestrator` is a single
   `Orchestrator()` instance created once at module import — it holds the shared OpenAI client, so
   it isn't rebuilt per request.

3. **The service layer does the actual work**, in
   [`services/search/orchestrator.py`](../../../src/jobs_intelligence_ai/services/search/orchestrator.py),
   as two stages (`Orchestrator.stream`, drained by `.run`):
   - **Stage 1 (retrieve):** `EmbeddingSearch.search_scored()` calls OpenAI's
     `vector_stores.search` (`file_search`) against the active country's vector store
     (`config.VECTOR_STORE_ID`) and returns a deterministic set of job ids — no model call, no DB
     yet.
   - **Stage 2 (grade):** `JobSearch.fetch(ids, filters)` pulls those ids' rows from MySQL in one
     query (via `infra/database.py`, against `Profile.read_view`), then `Grader.grade(...)` sends
     the whole batch to OpenAI once (`responses.parse` with a Structured Output schema) for
     authoritative scores/grades — one scoring call for the whole set, not one per job.

4. **The route wraps the result** back into `{ ok: true, count, jobs: [...] }` and Flask serializes
   it to JSON.

5. **The frontend renders it.** Back in `search.js`, `data.jobs` becomes the results table; no
   page reload happened — this is a single-page app, `index.html` never re-renders server-side
   after the initial load.

Every other feature blueprint (`saved`, `company`, `candidate`, `job_detail`, `interview`) follows
this same three-layer shape: **JS calls `api.*` → a thin blueprint route → a `services/*` module
that owns the MySQL/OpenAI calls.** Once you've read one end-to-end, the rest are the same pattern
with different services behind them.

---

## 6. One codebase, two countries

`config/profiles.py` defines a frozen `Profile` per country (DB schema, `read_view`/`jobs_table`,
column-name map, vector-store env var, feature flags). `config/settings.py` picks the active one
from the `COUNTRY` env var (or `--sk`/`--country` CLI flag, applied in `app.py:main()` **before**
anything else is imported) and re-exports its fields as flat module-level names — so the rest of
the app just imports `from jobs_intelligence_ai import config` and uses `config.COL`,
`config.DATABASE_URL`, `config.VECTOR_STORE_ID`, etc., without knowing which country is active.
Austria and Slovakia have real schema differences (SK has no `occupational_group`, a different
company table, reads a different view) — those are the columns listed in `Profile.absent_cols` and
guarded with `col_present()`.

---

## 7. Basic API calls — cheat sheet

The full reference is [API.md](../frontend/API.md); the shapes below are the ones you'll hit first
when poking at the app.

| Call | What it does |
|---|---|
| `POST /login` (form `username`/`password`) | Session login; seed users `admin`/`admin`, `Monika2`, `hr_manager` |
| `GET /api/filters` | Dropdown options for the search filter bar |
| `POST /api/match` `{ candidate_text, filters?, top_n? }` | Run the matching pipeline traced above → ranked jobs |
| `GET /api/company?name=` | Company hiring profile: stats + AI summary + contacts |
| `POST /api/saved` `{ job, ... }` | Save a job for the current candidate |
| `GET /api/saved/candidates` | List saved candidates (Saved tab) |
| `POST /api/candidate/parse-profile` `{ text }` | Turn raw CV text into a structured candidate profile |

All routes except `/login` and static files require a session (`before_request` in `app.py` checks
`session["user_id"]`); an unauthenticated `/api/*` call gets `401 { ok: false, error: "Unauthorized" }`
instead of a redirect. Every JSON response follows the same `{ ok: true, ... }` / `{ ok: false,
error: "..." }` envelope, which is exactly what `api.js`'s wrapper expects.

---

## 8. Where to go deeper

| Doc | For |
|---|---|
| [ARCHITECTURE.md](../ARCHITECTURE.md) | Full system overview, stack, two-database design, key design decisions |
| [API.md](../frontend/API.md) | Every route, by blueprint, with request/response shapes |
| [FRONTEND.md](../frontend/FRONTEND.md) | JS module map, tab layout, action-dispatch pattern, modals |
| [DATABASE.md](../infra/DATABASE.md) | Market DB vs app DB, column mappings, company-identity tiers |
| [services/search/](../services/search/) *(to document)* | Matching pipeline detail beyond §5 above |
| [services/reporting/README.md](../services/reporting/README.md) | AI company summaries + PDF reports |
| [services/candidate/README.md](../services/candidate/README.md) | Candidate store, CV/LinkedIn parsing |
| [TESTING.md](../TESTING.md) | Test layout and how to run them |
