# Restructure Plan — Modular Rework + Demo/Production Branches

> **Status:** Plan COMPLETE and execution-ready. Architecture, `shared/` (§4),
> config (§5), execution plan (§6), testing (§10), and all structural decisions (§9)
> agreed. Only the Stage 3 production feature set remains deferred. Nothing in §6 has
> run yet except Stage 1 (the `develop` branch). Running record.
>
> **STANDING RULE — docs track the code.** After each phase/step is done, update the
> documentation to reflect it *as part of that step* (before moving on): the mirrored
> `documentation/jobs_intelligence_ai/` module docs (§11), `TESTING.md`, and this plan's
> checkboxes/decisions log. A step isn't "done" until its docs are current.

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
│                    (FROM: chat.py top-level; AND search/orchestrator.py:59 made its own)
├── job.py        ◄ ★ canonical job dict: JOB_FIELDS map + serialize_job(row) [fresh]
│                    + overlay_job(job, row) [overlay] — kills the duplicated ~30-field
│                    mapping (FROM: search/utils.serialize_job + chat._apply_row)
├── grading.py    ◄ grade() + score→A/B/C banding  (FROM: search/utils.py; may fold into job.py)
└── taxonomy.py   ◄ sector/role taxonomy for the funnel  (FROM: taxonomy.py, top-level)
```

> **`json.py` dropped (superseded by Structured Outputs — see §6 2.1b).** The 3 JSON
> parsers existed only because the model was *asked in prose* for JSON, then its messy
> text was cleaned up. Switching the model calls to the SDK's `responses.parse(text_format=…)`
> (Pydantic, validated `output_parsed`) means replies are guaranteed-valid JSON — so the
> parsers are **deleted**, not merged. A residual `strip_citations` is added only if
> file_search-grounded structured text turns out to carry citation markers.

**Why each is shared (evidence from the code):**

| Item | Problem today |
|---|---|
| `llm.py`  | TWO OpenAI client paths: `chat.get_client()` singleton vs `search/orchestrator.py:59` `OpenAI(...)`. |
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

**Definition of done (per step):** code moved + tests green + **docs updated** (the
module's doc folder under §11, `TESTING.md` if tests changed, and this plan's checkbox).
Docs are part of the step, not a follow-up — see the STANDING RULE at the top.

**Structured Outputs is folded into repackaging, not a separate sweep.** When a module
(2.3) or blueprint (2.4) with LLM calls is repackaged, its model calls are converted to
`responses.parse(text_format=Pydantic)`, its hand-rolled JSON parser is deleted, and its
prompt drops the "respond with ONLY JSON" boilerplate — **plus TWO test layers (see §10):
offline unit tests** that mock the `responses.parse` boundary (happy path + refusal/failure
fallback) **and a live smoke test that ASSERTS** the real structured call works (valid,
sane `output_parsed`). Mocks prove the logic; the live smoke proves the call. One touch per file. By the end of Stage 2 the ~6 duplicate parsers and ~18 beg-for-JSON
call sites are all gone. (Audit: `parse_json`, `chat._parse/_parse_candidate`,
`interview_helper._parse_json`, `persona._parse_json_obj`, `profile_enricher._parse_json`,
+ inline `json.loads` in opportunity_briefing/candidate/analytics/company/radar/
report_generator/quality_classifier/seniority_classifier/saved/job_detail/search.)

**Verification legend** — run after each step:
- `pytest` = `pytest -m "not smoke"` (fast, no live API/DB)
- `smoke`  = `pytest -m smoke` (live OpenAI + MySQL; run when search-critical code moves)
- `boot`   = app imports + `create_app()` succeeds
- `tab`    = manually exercise the affected UI tab (the gate for service logic, since
  only `search` has automated coverage until 2.0 fills the rest)

- [x] **Stage 1 — Safe save.** Full codebase committed to `develop`, pushed. (`c7e52b8`)

### Stage 2 — Repackage into modules (on `develop`)

**2.0 — Test scaffold + foundation safety net** ✅ DONE *(before moving any code; see §10)*
- 2.0a ✅ Mirrored test tree (51 boilerplate `__init__`/`__main__` files) + shared infra:
  `_runner.py`, `_fake_db.py` (sync FakeEngine/Conn/Result/Row), `conftest.py` fixtures
  (`col`, `sample_job_row`, `fake_engine`), `_fixtures/samples.py`, `README.md`.
- 2.0b ✅ Pinning unit tests for the to-be-merged helpers — `shared/unit_tests/`:
  `test_1_json` (parse_json + _parse + _parse_candidate), `test_2_job` (serialize_job),
  `test_3_grading` (grade), `test_4_taxonomy`. Import the CURRENT paths; flip to `shared/`
  in 2.1 with identical asserts = equivalence guard.
- Gate: ✅ `pytest -m "not smoke"` = **26 passed, 1 deselected**. Baseline + foundation green.

**2.1 — Foundation `shared/`** (consolidate dup'd code; keep shims). One commit each:
- 2.1a ✅ `shared/llm.py` ← `get_client`; `chat.py` re-exports it (`_get_client` alias kept);
  `search/orchestrator` now calls it (2nd client path gone). Test `test_5_llm` added.
  Gate: ✅ import-smoke + `pytest -m "not smoke"` = **28 passed, 1 deselected**.
- 2.1b **Adopt Structured Outputs** — the standard for EVERY JSON-returning model call
  (replaces the planned `shared/json.py` merge): `client.responses.parse(text_format=Pydantic)`
  → validated `output_parsed`; delete the parser + the "respond with ONLY JSON" prompt
  boilerplate; add the two test layers (§10). Verified vs official docs + live SDK 2.30.0.
    - ✅ **grader** (the pilot — proves the pattern on the test-covered core). Pydantic
      `_Scores`; `test_grader` (5 offline) + `test_grader_smoke` (live, asserts). 29 passed.
    - **All remaining conversions are FOLDED INTO each module's repackaging** (2.2–2.4),
      one touch per file — see the **`SO →`** tag on each step below. Not a separate sweep.
  As each parser dies, retire its `test_1_json` case. By the end `parse_json`,
  `chat._parse/_parse_candidate`, and the per-service parsers are all gone; `shared/json.py`
  is NOT created (residual `strip_citations` only if a file_search call needs it).
- 2.1c `shared/job.py` ← `JOB_FIELDS` + `serialize_job(row)` [fresh] + `overlay_job(job,row)`
  [overlay]; `search/utils.serialize_job` + `chat._apply_row` delegate. Gate: `pytest`
  (equivalence tests) + `smoke`.
- 2.1d `shared/grading.py` ← `grade()`; `rescorer` + `search` delegate. Gate: `pytest`.
- 2.1e `shared/taxonomy.py` ← top-level `taxonomy.py`; importers (`core`, guided, stats)
  updated; old path shim. Gate: `pytest` + `boot`.

**2.2 — Relocate `search` + config cleanup**  *(decision: search moves under `services/`)*
- 2.2a ✅ Moved `search/` → `services/search/` (git rename); updated 7 src importers
  (`core`, rescorer, highlighter, cluster bp, search `__main__`/`__init__`) + 6 test imports;
  added package files to the moved test tree. Gate: ✅ `pytest -q` (incl. smoke) = **35 passed**.
- 2.2b ✅ Config cleanup (corrected after audit — most "tunables" were dead/cross-cutting):
  **deleted** 7 dead constants (`DEFAULT_TOP_N`, `MAX_TOP_N`, `MATCH_CYCLES`, `MAX/MIN_MATCH_CYCLES`,
  `MATCH_WAVE_SIZE`, `MATCH_CONVERGE_NEW` — zero readers); **moved** `MAX_NUM_RESULTS` → search-owned
  constant in `services/search/config.py`; **kept** `SCORE_A_MIN/B_MIN` in global (cross-cutting:
  grader + rescorer + cluster bp → they go to `shared/grading` at 2.1d, not search). search keeps
  its dataclasses for now. Gate: ✅ import-smoke + 31 offline (value-preserving — `MAX_NUM_RESULTS`=30 unchanged).
- 2.2c ✅ Investigated the legacy `EMBEDDING_PROMPT` ids path (`embedding_search.search()`).
  It's **reachable** (the `direct_retrieval=False` A/B path), not dead, works via `parse_json`,
  and has no test → **left as-is**. Its `parse_json` retires with the chat-search conversion
  (#4, same `file_search`+SO pattern) or if the A/B path is dropped (product call). **Probed
  live: `file_search` + Structured Outputs coexist** ✅ (call accepted, returns parsed object;
  ids empty in the quick probe → prompt tuning needed, but the API combo is confirmed) — this
  de-risks chat #4.

**2.3 — Services, one module per commit** (least → most entangled). Each: create package
(`__init__` = public API, `config.py` if needed, `orchestrator.py`, helpers, `__main__`
where meaningful), move code, repoint importing blueprint(s) + service↔service imports,
add `unit_tests/`. Gate per module: `pytest` + `boot` + `tab`.

**`SO →`** column = the LLM calls in that module to convert to Structured Outputs in the
SAME step (delete its JSON parser + prompt boilerplate, add the two test layers per §10).
"verify" = has a model call I haven't confirmed parses JSON — check when repackaging.

| # | Module ← current files | Importers to repoint | `SO →` convert |
|---|---|---|---|
| 1 | `stats/` ← opportunity, quality_score, salary_stats | (already grouped; add API + `__main__`) | — none (pure stats) |
| 2 | `enrichment/` ← seniority_classifier, quality_classifier, match_insights, rescorer, highlighter | search bp, saved bp, `core`, chat.enrich | **rescorer**, **highlighter** (drop `parse_json`); verify seniority/quality_classifier/match_insights |
| 3 | `interview/` ← interview_helper | interview bp | **interview_helper** (`_parse_json`) |
| 4 | `reporting/` ← report_generator, report_pipeline, opportunity_briefing | analytics bp, saved bp, radar bp | **opportunity_briefing** (`json.loads` ×2); verify report_generator/pipeline |
| 5 | `chat/` ← send_message/_parse, send_job_message, send_candidate_message, enrich_jobs_from_db | chat bp, job_detail bp, `core` | **send_message** (`_parse`, file_search+SO confirmed in 2.2c — tune prompt), **send_candidate_message** (`_parse_candidate`); job/segment msgs are text-only |
| 6 | `clustering/` ← clustering, persona, + send_segment_message | cluster bp | **persona** (`_parse_json_obj`); clustering.py = embeddings, no parse |
| 7 | `candidate/` ← candidate_store, example_cv, profile_enricher | candidate bp, guided bp, saved bp, cluster bp | **profile_enricher** (`_parse_json`); verify example_cv |
| 8 | `geo/` ← at_geo  *(grouping: confirm)* | map/radar consumers | — none (geo lookup) |
| 9 | `auth/` ← auth  *(grouping: confirm)* | `frontend/app.py` factory | — none (DB only) |

**2.4 frontend** also carries `SO →`: the blueprint-level model calls convert during the
frontend repackaging — `candidate`, `analytics`, `company`, `radar` (`chat.completions` →
`beta.chat.completions.parse` or `responses.parse`), `cluster` (`parse_json`), `saved`,
`job_detail` (×5), `search` bp. Same rule: convert + delete parser + two test layers.

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
- ✅ `shared/` (§4): `llm` + `job` + `grading` + `taxonomy`; unifies 2 client paths and the duplicated ~30-field job mapping.
- ✅ **Structured Outputs (2.1b)**: JSON-returning model calls use `responses.parse(text_format=Pydantic)` → `output_parsed`. Deletes the 3 JSON parsers (no `shared/json.py`). Verified vs official docs + live SDK 2.30.0. `pydantic` added to deps. ✅ file_search + structured outputs confirmed to coexist (probed live in 2.2c) — chat #4 unblocked (needs prompt tuning, not an API change).
- ✅ Config (§5): flat module constants per service; global = environment/identity layer (not aggregator); move matching tunables into `services/search/config.py`. Dataclasses dropped.
- ✅ Execution plan (§6): ordered, commit-per-step, shim-based, verify after each. Test scaffold (2.0) goes first.
- ✅ Testing (§10): full coverage scope — mirrored test tree, **a test package per service** (mirrors the API principle), unit tests with `_fake_db` + mocked `shared/llm` client; fake-DB now, docker integration later.
- ✅ Documentation (§11): `documentation/` mirrors the package, one folder per module (`Work` convention); docs realigned to the target structure; `TESTING.md` added.
- ✅ `search/` moves under `services/search/` (2.2a).
- ✅ `core/` facade dissolved into per-service `__init__` APIs (2.5).
- ✅ `geo` + `auth` as their own `services/` modules.
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

---

## 11. Documentation layout — AGREED (docs mirror the package)

Same principle as `tests/`: **`documentation/jobs_intelligence_ai/` mirrors
`src/jobs_intelligence_ai/`** — one doc folder per module (foundation / services /
frontend), empty ones holding a `.gitkeep` until documented (the `Work` convention).
Cross-cutting + planning docs (`README`, `ARCHITECTURE`, `TESTING`, `RESTRUCTURE_PLAN`,
`CLEANUP_PLAN`) stay at the top level.

Realigned to the target structure (docs lead the code so the end state is documented up front):

| Doc | Was | Now |
|---|---|---|
| `DATABASE.md` | `core/` | `infra/` |
| `SALARY_ANALYSIS.md` | `stats/` | `services/stats/` |
| `API.md`, `FRONTEND.md` | `web/` | `frontend/` |
| `INTERVIEW_REWORK_CHANGELOG.md` | top level | `services/interview/` |
| `TESTING.md` | — | top level (new — documents §10) |

Each module gets its own doc folder; new module docs land beside the code as it's
repackaged in Stage 2.3 / 2.4. `README.md` is the mirror index.
