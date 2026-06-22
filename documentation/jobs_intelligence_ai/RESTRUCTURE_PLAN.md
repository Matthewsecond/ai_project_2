# Restructure Plan — Modular Rework + Demo/Production Branches

> **Status:** Planning. Architecture, `shared/` (§4), config (§5), execution plan (§6)
> and testing (§10) all agreed. **Confirm before executing:** `search/`→`services/`,
> `core/` dissolution, `geo`/`auth` grouping (the 🟡 items in §9). Production feature set
> (Stage 3) still deferred. Nothing in §6 has run yet except Stage 1. Running record.

---

## 1. Why we're doing this

We're entering the demo phase. The demo must show only **essentials that are
stable**; most current features are experimental and not demo-ready. Two needs:

1. **Branch separation** — a lean, shippable codebase to demo from, kept clean of
   half-built features, plus a place to keep building everything else.
2. **Real modules** — `src/` is currently organized *horizontally by layer*
   (`services/` is a flat dump of 16 files, with stray `chat.py` / `taxonomy.py`
   at the top). We want proper self-contained modules, mirroring the convention
   in `C:\Users\roman\PycharmProjects\Work\src\pipelines` (each sub-domain is a
   package with `__init__` / `__main__` / `config` / `orchestrator` + helpers,
   plus a shared/ foundation).

---

## 2. Branch strategy (classic two-branch GitFlow)

**Two branches, not three.** `master` *is* the production/stable branch — no
separate `production` branch (that was redundant; dropped).

| Branch | Role | State |
|---|---|---|
| `develop` | Everything, incl. experimental. Day-to-day work. | **Created + pushed** (commit `c7e52b8`). Holds the full src/ codebase. |
| `master` | Stable / production / demo. What we ship. | Currently still the stale old `demo_real/` layout. Gets **replaced with the lean app at Stage 3**. GitHub default branch. |

**Workflow:** build on `develop`; when a feature matures, promote *just that
feature* onto `master`.

**The gotcha we're avoiding:** if `master` were just `develop` with files
*deleted*, merging a matured feature later would drag the deleted files back in.
So `master` is the **base** and `develop` adds features *on top*; promotion is
done by cherry-pick / per-feature merge, not by subtracting. Once features are
clean packages (this rework), promoting one = adding/removing a folder. That's
the payoff that makes the branch split trivial.

---

## 3. Target architecture — three layers

A feature is a **folder, not a file scattered across layers**. The frontend
consumes services; services stand on the foundation; **a service never imports
the frontend, and never reaches sideways into another service.**

```
src/jobs_intelligence_ai/
├── __main__.py                 # entry point

│  ── FOUNDATION ("basic functionality") ─────────────────────────
├── config/                     # app-wide settings + country profiles   (see §5 — OPEN)
├── infra/                      # I/O plumbing: database, integrations/linkedin
├── shared/                     # reusable code + domain (see §4)

│  ── SERVICES (each a self-contained module, see §7 pattern) ─────
├── services/
│   ├── search/                 # ✅ already proper — the template
│   ├── clustering/             # clustering + persona
│   ├── interview/              # interview_helper
│   ├── reporting/              # report_generator + report_pipeline + opportunity_briefing
│   ├── candidate/              # candidate_store + example_cv + profile_enricher
│   ├── enrichment/             # seniority + quality_classifier + match_insights + rescorer + highlighter
│   ├── stats/                  # salary_stats + quality_score + opportunity
│   ├── geo/                    # at_geo                      (grouping TBD)
│   └── auth/                   # auth
│
│  ── FRONTEND (own layer; thin routes that call services) ────────
└── frontend/                   # rename of web/
    ├── app.py                  # create_app(), register_blueprints
    ├── blueprints/             # one per tab — parse request → call service → jsonify
    └── templates/
```

---

## 4. `shared/` — ✅ AGREED (expanded after reading the code)

Contents derived from the **actual import graph + duplication found in the code**.
Several things are either trapped in the wrong place or copy-pasted across modules:

```
shared/
├── __init__.py
├── llm.py        ◄ get_client() OpenAI client singleton — replaces BOTH client paths
│                    (FROM: chat.py top-level; AND search/orchestrator.py:59 makes its own)
├── json.py       ◄ LLM-response JSON extraction: parse_json (array) + parse_object
│                    (fenced) + citation-marker stripping
│                    (FROM: search/utils.parse_json + chat._parse/_parse_candidate)
├── job.py        ◄ ★ canonical job dict: JOB_FIELDS map + serialize_job(row) [fresh]
│                    + overlay_job(job, row) [overlay] — kills the duplicated ~30-field
│                    mapping (FROM: search/utils.serialize_job + chat._apply_row)
├── grading.py    ◄ grade() + score→A/B/C banding  (FROM: search/utils.py; may fold into job.py)
└── taxonomy.py   ◄ sector/role taxonomy for the funnel  (FROM: taxonomy.py, top-level)
```

**Why each is shared (evidence from the code):**

| Item | Problem today |
|---|---|
| `llm.py`  | TWO OpenAI client paths: `chat.get_client()` singleton vs `search/orchestrator.py:59` `OpenAI(...)`. |
| `json.py` | 3 near-identical fenced-JSON extractors: `search/utils.parse_json`, `chat._parse`, `chat._parse_candidate`. |
| `job.py`  | **~30-field DB-row→job-dict mapping copy-pasted** in `search/utils.serialize_job` AND `chat._apply_row`. Drift hazard. |
| `grading.py` | `grade()` imported by `search` + `rescorer`. |
| `taxonomy.py` | role/sector taxonomy used by guided funnel + search/stats. |

`serialize_job` builds a fresh dict (defaults `"Untitled"`/`"Unknown"`); `_apply_row`
overlays onto an existing dict (`… or e.get(field)`). So `job.py` exposes one field
map with two entry points: `serialize_job(row)` [fresh] and `overlay_job(job, row)` [overlay].

**Deliberately NOT shared yet** (single caller — revisit when a 2nd appears): the
`loc = "city, state"` join, `score_pct` formatting, the UTF-8 console fix,
`_LANG_INSTRUCTIONS`.

`config/` and `infra/` stay as **sibling foundation packages** next to `shared/`
(distinct concerns: settings vs I/O vs reusable code).

---

## 5. Config — ✅ AGREED (flat constants; global = environment layer)

Decided after checking real usage: the search dataclasses (`SearchConfig` etc.) are
only ever instantiated as `SearchConfig()` defaults (`orchestrator.py:48` is the sole
caller, never overrides) — so the dataclass overridability is unused complexity. And
the `Work/pipelines` convention for per-module config is **flat module constants**
(`company_match/config.py`: `LLM_MODEL = "gpt-5.4"`, …), not dataclasses.

**Two levels, dependency points ONE way (module → global; global never imports modules):**

- **Global** (`config/`) = **environment & identity** — *what/where am I running*:
  country profile + `COL` mapping + feature flags, secrets/connections
  (`OPENAI_API_KEY`, `DATABASE_URL`, `VECTOR_STORE_ID`, Apify), shared model defaults
  (`CHAT_MODEL`), Flask runtime. **Not an aggregator** of module configs (that would
  reverse the dependency, re-bloat global, and load everything to run one thing).
- **Per-service** (`<service>/config.py`) = **behaviour** — *how this feature acts*:
  thresholds, cycle counts, prompts, granularity. **Flat module constants**, reading
  the shared bits from global (e.g. `model = config.CHAT_MODEL`).

**Test for "is it global?":** would every country/deployment change it the same way?
If no, it's module-level.

**Concrete cleanup (proves the split):** the matching tunables currently mis-filed in
global `config/settings.py` move **into `services/search/config.py`** as flat constants:
`SCORE_A_MIN, SCORE_B_MIN, DEFAULT_TOP_N, MAX_TOP_N, MATCH_CYCLES, MAX_MATCH_CYCLES,
MIN_MATCH_CYCLES, MATCH_WAVE_SIZE, MATCH_CONVERGE_NEW, MAX_NUM_RESULTS`. (`search/config.py`
already re-reads `SCORE_A_MIN` from global — that indirection disappears once search owns it.)

**Dataclasses:** dropped by default. Re-introduce only for a service that genuinely needs
runtime-swappable / injectable config (none do today).

---

## 6. Execution stages

**Core principle:** every sub-step is its own commit and **leaves the app working**.
Moves use **re-export shims** at the old import paths so existing callers keep working
until migrated; shims are deleted only in the final cleanup (2.6). No "broken in the
middle" state.

**Verification legend** — run after each step:
- `pytest` = `pytest -m "not smoke"` (fast, no live API/DB)
- `smoke`  = `pytest -m smoke` (live OpenAI + MySQL; run when search-critical code moves)
- `boot`   = app imports + `create_app()` succeeds
- `tab`    = manually exercise the affected UI tab (the gate for service logic, since
  only `search` has automated coverage until 2.0 fills the rest)

- [x] **Stage 1 — Safe save.** Full codebase committed to `develop`, pushed. (`c7e52b8`)

### Stage 2 — Repackage into modules (on `develop`)

**2.0 — Test scaffold + foundation safety net** *(before moving any code; see §10)*
- 2.0a Lay down the mirrored test tree (folders + `__init__`/`__main__` per module) and
  shared infra: `_fake_db.py`, `conftest.py` fixtures, `_fixtures/` sample data (a job DB
  row, a CV, sample LLM responses), `README.md`.
- 2.0b Write unit tests **pinning the CURRENT behavior** of the to-be-merged helpers:
  both job mappings (`serialize_job` / `_apply_row`), the 3 JSON parsers, `grade()`.
  These are the equivalence check for 2.1.
- Gate: `pytest` green against today's code.

**2.1 — Foundation `shared/`** (consolidate dup'd code; keep shims). One commit each:
- 2.1a `shared/llm.py` ← `get_client`; `chat.py` + `core` re-export it; point
  `search/orchestrator.py:59` at it (kills the 2nd client). Gate: `pytest` + `boot`.
- 2.1b `shared/json.py` ← `parse_json` (array, from `search/utils`) + `parse_object`
  (fenced, from `chat._parse`/`_parse_candidate`) + citation stripping; old sites delegate.
  Gate: `pytest`.
- 2.1c `shared/job.py` ← `JOB_FIELDS` + `serialize_job(row)` [fresh] + `overlay_job(job,row)`
  [overlay]; `search/utils.serialize_job` + `chat._apply_row` delegate. Gate: `pytest`
  (equivalence tests) + `smoke`.
- 2.1d `shared/grading.py` ← `grade()`; `rescorer` + `search` delegate. Gate: `pytest`.
- 2.1e `shared/taxonomy.py` ← top-level `taxonomy.py`; importers (`core`, guided, stats)
  updated; old path shim. Gate: `pytest` + `boot`.

**2.2 — Relocate `search` + config cleanup**  *(decision: search moves under `services/`)*
- 2.2a Move top-level `search/` → `services/search/`; update importers (`core`, cluster bp,
  shims) and the test path `tests/.../search/` → `tests/.../services/search/`. Gate: `pytest` + `smoke` + `boot`.
- 2.2b Move matching tunables from `config/settings.py` → `services/search/config.py` as
  flat constants (search owns them; drop the global re-read). search keeps its existing
  dataclasses for now (works; flattening = low-payoff, deferred). New services use flat
  constants. Gate: `pytest`.

**2.3 — Services, one module per commit** (least → most entangled). Each: create package
(`__init__` = public API, `config.py` if needed, `orchestrator.py`, helpers, `__main__`
where meaningful), move code, repoint importing blueprint(s) + service↔service imports,
add `unit_tests/`. Gate per module: `pytest` + `boot` + `tab`.

| # | Module ← current files | Importers to repoint |
|---|---|---|
| 1 | `stats/` ← opportunity, quality_score, salary_stats | (already grouped; add API + `__main__`) |
| 2 | `enrichment/` ← seniority_classifier, quality_classifier, match_insights, rescorer, highlighter | search bp, saved bp, `core`, chat.enrich |
| 3 | `interview/` ← interview_helper | interview bp |
| 4 | `reporting/` ← report_generator, report_pipeline, opportunity_briefing | analytics bp, saved bp, radar bp |
| 5 | `chat/` ← send_message/_parse, send_job_message, send_candidate_message, enrich_jobs_from_db | chat bp, job_detail bp, `core` |
| 6 | `clustering/` ← clustering, persona, + send_segment_message | cluster bp |
| 7 | `candidate/` ← candidate_store, example_cv, profile_enricher | candidate bp, guided bp, saved bp, cluster bp |
| 8 | `geo/` ← at_geo  *(grouping: confirm)* | map/radar consumers |
| 9 | `auth/` ← auth  *(grouping: confirm)* | `frontend/app.py` factory |

**2.4 — Frontend** (`web/` → `frontend/`)
- Rename `web/` → `frontend/`. Update `web/__init__` registry, `app.py`, top-level
  `__main__.py`, and **`pyproject.toml`**: `[project.scripts]` `…web.app:main` →
  `…frontend.app:main`, package-data `web/templates/*.html` → `frontend/templates/*.html`;
  then `pip install -e .` to refresh the entry point. Thin blueprints to call service public
  APIs. Add `frontend/integration_tests/` (Flask `test_client`). Gate: `boot` + console
  script + `tab` + integration tests.

**2.5 — Dissolve `core/` + remove shims**  *(decision: dissolve the facade)*
- Repoint remaining `from …core import` users to the service packages' own `__init__` APIs;
  delete `core/`. Remove all re-export shims (chat remnants, `search/utils` delegations,
  old `taxonomy.py`). Gate: full `pytest` + `smoke` + `boot` + `tab`.

- [ ] **Stage 3 — Make `master` the lean app.** Bring only matured modules onto `master`
      (search + whatever basics we bless — deferred), replacing the old `demo_real/` content. Push.

---

## 7. Services-module pattern — AGREED

Modeled on the existing `search/` module. Example, `clustering/` (today: loose
`services/clustering.py` + `services/persona.py` + route logic in
`web/blueprints/cluster.py`):

```
services/clustering/
├── __init__.py        # docstring + public API note
├── __main__.py        # python -m ...services.clustering <cv_folder> → prints segments
├── config.py          # ClusteringConfig: granularity, EMBEDDING_MODEL, linkage…
├── orchestrator.py    # single public entry: ClusterEngine.run(profiles) → segments
├── embeddings.py      # embed_profiles()                  (from clustering.py)
├── segmenting.py      # Ward-linkage dendrogram cut        (from clustering.py)
└── persona.py         # persona labelling of each segment  (from persona.py)
```

Conventions:
- `orchestrator.py` = the one public class the frontend calls.
- `config.py` = the service's tunables (Level 2, §5).
- `__main__.py` = standalone runner **where running alone is meaningful**
  (search, clustering: yes; auth: optional smoke test). Not dogmatic.
- Helpers split by job; the blueprint shrinks to: parse request → call
  orchestrator → jsonify, and lives in `frontend/`.

---

## 8. Current → target file map (full)

| Today | Target |
|---|---|
| `chat.py` → `get_client` | `shared/llm.py` |
| `chat.py` → send_message/_parse, send_job_message, send_candidate_message, enrich_jobs_from_db | `services/chat/` |
| `chat.py` → send_segment_message | `services/clustering/` |
| `taxonomy.py` | `shared/taxonomy.py` |
| `search/utils.py` (parse_json, serialize_job, grade) | `shared/json.py`, `shared/job.py`, `shared/grading.py` |
| `core/` (facade re-exporting chat/search/services) | **dissolved** — each service `__init__` is its own public API |
| `config/` | `config/` = environment layer; matching tunables move OUT to `services/search/config.py` (§5) |
| `infra/`, `integrations/linkedin.py` | `infra/` (+ `infra/integrations/`) |
| `search/` | `services/search/` (move under umbrella — §6 step 2.2a) |
| `services/clustering.py` + `persona.py` | `services/clustering/` |
| `services/interview_helper.py` | `services/interview/` |
| `services/report_generator.py` + `report_pipeline.py` + `opportunity_briefing.py` | `services/reporting/` |
| `services/candidate_store.py` + `example_cv.py` + `profile_enricher.py` | `services/candidate/` |
| `services/seniority_classifier.py` + `quality_classifier.py` + `match_insights.py` + `rescorer.py` + `highlighter.py` | `services/enrichment/` |
| `stats/{opportunity,quality_score,salary_stats}.py` | `services/stats/` |
| `services/at_geo.py` | `services/geo/` (grouping TBD) |
| `services/auth.py` | `services/auth/` |
| `web/` (app, blueprints, templates) | `frontend/` |

Note: `python -m jobs_intelligence_ai.search` becomes `…services.search` after 2.2a.

---

## 9. Decisions log

- ✅ Branch model: TWO branches — `master` (stable, the base) + `develop` (everything, on top). No separate `production`.
- ✅ Three-layer architecture (foundation / services / frontend).
- ✅ Services-module pattern (§7).
- ✅ `tests/` + `documentation/` stay at **repo root** as siblings of `src/`, mirroring the package (matches Work convention; already true today). Not nested in `src/`.
- ✅ `shared/` (§4): `llm` + `json` + `job` + `grading` + `taxonomy`; unifies 2 client paths, 3 JSON parsers, and the duplicated ~30-field job mapping.
- ✅ Config (§5): flat module constants per service; global = environment/identity layer (not aggregator); move matching tunables into `services/search/config.py`. Dataclasses dropped.
- ✅ Execution plan (§6): ordered, commit-per-step, shim-based, verify after each. Test scaffold (2.0) goes first.
- ✅ Testing (§10): full coverage scope — mirrored test tree, **a test package per service** (mirrors the API principle), unit tests with `_fake_db` + mocked `shared/llm` client; fake-DB now, docker integration later.
- 🟡 `search/` moves under `services/` (2.2a) — **proposed in the plan; confirm.**
- 🟡 `core/` facade dissolved into per-service `__init__` APIs (2.5) — **proposed; confirm.**
- 🟡 `geo` + `auth` as their own `services/` modules — **proposed; confirm.**
- ⚠ Production feature set (Stage 3) — deferred, not chosen.

---

## 10. Testing strategy — AGREED (scope A: full net)

Mirrors the `Work/tests` convention: the **test tree mirrors the source tree**, each
module is its own **test package** (`__init__` + `__main__`, runnable in isolation —
this mirrors the public-API principle), split into `unit_tests/` · `integration_tests/`
· `smoke_tests/` as needed, with numbered files (`test_1_*.py`).

```
tests/
├── __init__.py  __main__.py  README.md
├── conftest.py                 # shared fixtures
├── _fake_db.py                 # fake SQLAlchemy conn — unit tests, no live DB (Work pattern)
├── _fixtures/                  # sample job row, sample CV, sample LLM responses
├── (_dbtest/  docker MySQL — LATER, only if an integration test needs a real DB)
└── jobs_intelligence_ai/
    ├── shared/unit_tests/      # test_1_json · test_2_job · test_3_grading · test_4_taxonomy
    ├── services/
    │   ├── search/{unit_tests,smoke_tests}   # exists — keep (moves under services/ at 2.2a)
    │   ├── stats/ enrichment/ interview/ reporting/ chat/ clustering/ candidate/ geo/ auth/
    │   │        └── unit_tests/              # one test package per service
    └── frontend/integration_tests/          # Flask test_client route tests
```

**The two seams that make services unit-testable** (and a bonus reason for `shared/`):
- **`shared/llm.get_client()`** — the single OpenAI client entry point → mock it once,
  every service's LLM path is testable without network.
- **`_fake_db`** — fake SQLAlchemy connection (records SQL, returns canned rows) → DB
  logic testable without MySQL.

**Tier guide:**
- `unit_tests/` — pure logic; `shared/` (no mocks needed), services (mock `get_client`
  + use `_fake_db`). The bulk of coverage.
- `integration_tests/` — wired components, e.g. `frontend` routes via Flask `test_client`
  with services mocked.
- `smoke_tests/` — live OpenAI + MySQL (marked `@pytest.mark.smoke`, excluded by default).
  `search` already has one.

**Equivalence-first rule (2.0b):** before merging duplicated code into `shared/`, write
tests that pin the *current* output of the old functions, so the merge is provably
behavior-preserving (esp. the `serialize_job` / `_apply_row` → `shared/job.py` unification).
