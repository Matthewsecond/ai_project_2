# Restructure Plan — Modular Rework + Two-Branch Demo Split

> **Status: ✅ COMPLETE — superseded as the active plan (2026-06-29).** The modular
> rework is fully done (Stages 1–2.6). The product phase that this plan deferred as
> "Stage 3" is now tracked in [FRONTEND_DB_REWORK_PLAN.md](FRONTEND_DB_REWORK_PLAN.md) —
> **use that for current work.** Kept here as the completed record; its branch strategy
> (§2) and lean-`master` snapshot composition are still the operative deployment model,
> referenced by the active plan.
>
> _Historical status:_ Architecture, `shared/` (§4), config (§5), execution plan (§6),
> testing (§10), and all structural decisions (§9) agreed; backend Stages 2.0–2.5 done
> (`core/` dissolved, `shared/` = llm+grading+taxonomy, zero shims), frontend 2.6 closed.
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
├── config/                     # app-wide settings + country profiles   (see §5)
├── infra/                      # I/O plumbing: database + integrations/linkedin
├── shared/                     # reusable code + domain (see §4)

│  ── SERVICES (each a self-contained module, see §7 pattern) ─────
├── services/
│   ├── search/                 # ✅ the template (convergence search + job_chat + match_analysis)
│   ├── clustering/             # clustering + persona + segment_chat
│   ├── interview/              # interview_helper
│   ├── reporting/              # report_generator + report_pipeline + opportunity_briefing + session/company
│   ├── candidate/              # store + example_cv + profile_enricher + profile_parser + assistant + guided_builder
│   ├── enrichment/             # seniority + quality_classifier + match_insights + rescorer + highlighter + observation
│   ├── job_detail/             # per-job modal AI tools (translate/compact/outreach/cv-questions/strength)
│   ├── stats/                  # salary_stats + quality_score + opportunity
│   ├── geo/                    # at_geo
│   └── auth/                   # auth (→ accounts)
│
│  ── FRONTEND (own layer; thin routes that call services) ────────
└── frontend/                   # rename of web/
    ├── app.py                  # create_app(), register_blueprints
    ├── blueprints/             # one per tab — parse request → call service → jsonify
    └── templates/
```

---

## 4. `shared/` — ✅ DONE (final shape differs from the original plan — see notes)

Contents derived from the **actual import graph + duplication found in the code**.
**As built (after 2.5):** `shared/` = `llm` + `grading` + `taxonomy`. The originally-planned
`json.py` and `job.py` were both dropped (see strikethrough below) — neither's justification survived
the rest of the rework.

```
shared/
├── __init__.py
├── llm.py        ◄ get_client() OpenAI client singleton — replaces BOTH client paths   ✅
│                    (FROM: chat.py top-level; AND search/orchestrator.py:59 made its own)
├── (job.py)      ◄ ❌ DROPPED — was justified by serialize_job vs chat._apply_row duplication;
│                    _apply_row deleted with job-search chat (#5), so serialize_job is single-domain
│                    now. Stays in services/search/utils.py.
├── grading.py    ◄ grade() + score→A/B/C banding  (FROM: search/utils.py)              ✅ (2.5)
└── taxonomy.py   ◄ sector/role taxonomy for the funnel  (FROM: taxonomy.py, top-level)  ✅ (2.5)
```

> **`json.py` dropped (superseded by Structured Outputs — see §6 2.1b).** The 3 JSON
> parsers existed only because the model was *asked in prose* for JSON, then its messy
> text was cleaned up. Switching the model calls to the SDK's `responses.parse(text_format=…)`
> (Pydantic, validated `output_parsed`) means replies are guaranteed-valid JSON — so the
> parsers are **deleted**, not merged. A residual `strip_citations` is added only if
> file_search-grounded structured text turns out to carry citation markers.

**Why each is shared (evidence from the code):**

| Item | Problem it solved |
|---|---|
| `llm.py` ✅ | TWO OpenAI client paths: `chat.get_client()` singleton vs `search/orchestrator.py:59` `OpenAI(...)`. Unified. |
| ~~`job.py`~~ ❌ | Was: ~30-field DB-row→job-dict mapping copy-pasted in `search/utils.serialize_job` AND `chat._apply_row`. **`_apply_row` deleted with job-search chat (#5)**, so the duplication is gone and `serialize_job` is single-domain — `job.py` dropped, stays in `search/utils.py`. |
| `grading.py` ✅ | `grade()` was imported by `search` + `rescorer` (a service→service sideways import). Now in `shared/` (2.5). |
| `taxonomy.py` ✅ | role/sector taxonomy used by the guided funnel. Moved from top-level (2.5). |

**Deliberately NOT shared** (single caller — revisit when a 2nd appears): the
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
until migrated; shims are deleted in the **2.5** cleanup (turned out there were none left to
delete — see 2.5). No "broken in the middle" state.

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
- 2.1b ✅ **DONE** (grader pilot + all conversions folded into 2.2–2.4, now COMPLETE). One
  documented residual: `embedding_search.search()` keeps `utils.parse_json` because its `file_search`
  tool response returns citation-marked `output_text` that can't go through `responses.parse`.
  **Adopt Structured Outputs** — the standard for EVERY JSON-returning model call
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
- 2.1c ❌ **DROPPED** (done as part of 2.5 analysis). `shared/job.py` was justified only by the
  `serialize_job` vs `chat._apply_row` duplication — and `_apply_row` was deleted with the job-search
  chat (#5). `serialize_job` is now single-domain (search only), so a `shared/job.py` would be ceremony
  with no second caller. Left in `services/search/utils.py`.
- 2.1d ✅ **DONE (in 2.5)** `shared/grading.py` ← `grade()` (pure; thresholds stay caller-supplied from
  global config per §5). Repointed `search/grader`, `enrichment/rescorer` (kills the search→enrichment
  sideways import), cluster bp; `test_3_grading` flipped to the new path. Gate: ✅ 182 passed.
- 2.1e ✅ **DONE (in 2.5)** `shared/taxonomy.py` ← top-level `taxonomy.py` (`git mv`); guided bp +
  `test_4_taxonomy` repointed; no shim (the only other importer was the now-deleted `core`). Gate: ✅ boot + 182 passed.

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

**2.3 — Services, one module per commit** ✅ **COMPLETE (all 9 done).** Each: create package
(`__init__` = public API, **`config.py` always**, `orchestrator.py`, helpers, `__main__`
where meaningful), move code, repoint importing blueprint(s) + service↔service imports,
add `unit_tests/`. Gate per module: `pytest` + `boot` + `tab`. The top-level `chat.py` was
dissolved across #5–#7 (distribute-by-domain). Offline gate after #9: **130 passed, 17 deselected.**
Next: **2.4 frontend** (`web/`→`frontend/`, blueprint SO conversions, + the deferred dead
job-search-chat JS cleanup), then **2.5** (dissolve `core/`, remove shims).

**2.4 — ✅ COMPLETE.** Done: ① `web/`→`frontend/` rename (package, entry point, docs).
② candidate bp `parse-profile` → `services/candidate/profile_parser.py` (SO `CandidateProfile`).
③ analytics + radar chats → `services/reporting/session_chat.py` (SO `AdvisorReply`, single
prose field; killed the last `chat.completions` + raw `OpenAI()` in those bps).
④ company summary → `services/reporting/company_summary.py` (SO `CompanySummary`, single prose
field; returns "" on error since the summary is optional).
⑤ cluster overview + grade-job → `services/clustering/segment_analysis.py` (SO: prose
`SegmentOverview` + JSON `CandidateGrades` list; the latter kills the last `parse_json` caller
in a blueprint).
⑥ guided builder two-pass chat → `services/candidate/guided_builder.py` (SO `GuidedFieldUpdates`
extract + `GuidedReply` reply/chips). Moves the **guided** bp off the `_gpt_json` helper it
borrowed from the saved bp (no blueprint imports another blueprint anymore) — committed first so
boot stays green when ⑦ removes that helper. Blueprint keeps all grounding (DB faceting, taxonomy
catalog, salary benchmark, chip-routing).
⑦ saved bp HR profile-override chat → `services/enrichment/observation.py` (SO
`ObservationOverrides` extract + single-prose `ObservationReply`; replaced two `responses.create`
+ `json.loads` calls behind two "ONLY JSON" prompts). Deletes the now-unused shared `_gpt_json`
helper.
⑧ job_detail modal tools → `services/job_detail/` (5 calls: translate / compact / cv-questions /
outreach → single-prose `JobDetailText`; candidate-strength → `CandidateStrength`, which kills the
**last "Return ONLY valid JSON" + `json.loads` in a blueprint**). All five were inline
`responses.create`; now service functions on `shared.get_client` via `responses.parse`; blueprint
thins to validate → call → jsonify.
⑨ search bp match-analysis → `services/search/match_analysis.py` (the candidate-vs-matched-jobs
assessment; prose → single-field `MatchAnalysis`, surfaced via `core`). This was the **last inline
blueprint LLM call** — every blueprint model call now lives in a service on `responses.parse`.
⑩ `frontend/integration_tests/` — real Flask `test_client` (auth-gate 401/redirect + the thinned
2.4 routes: validation 400 / mocked-service 200 / service-error 500), `auth.init_db` stubbed and
services mocked at the blueprint boundary (no OpenAI/DB). Offline gate: **182 passed, 31 deselected.**
⑪ ✅ dead job-search-chat JS removed from `index.html` (~456 lines; verified in-app — login/reload/all-5-tabs
console-clean, dead identifiers gone, live `.chat-*`/`SESSION_ID` islands intact). Committed `b6b287d`.

**Every service module gets its own `config.py`** (mirrors the `pipelines` convention) —
the single home for that module's settings: model choice, prompts, thresholds, feature
flags, and (for Structured-Outputs services) its Pydantic schemas, as flat constants (§5).
Even small/pure services get one (e.g. `stats/config.py` for bin sizes / score weights),
so there's always one obvious place to look for a module's knobs.

**`SO →`** column = the LLM calls in that module to convert to Structured Outputs in the
SAME step (delete its JSON parser + prompt boilerplate, add the two test layers per §10).
"verify" = has a model call I haven't confirmed parses JSON — check when repackaging.

| # | Module ← current files | Importers to repoint | `SO →` convert |
|---|---|---|---|
| 1 | ✅ `stats/` ← opportunity, quality_score, salary_stats | radar bp, search bp, quality_classifier → package API | — none (pure stats); +`config.py`, `__init__` API, `__main__`, 14 offline tests; found 2 quality_score bugs (flagged) |
| 2 | ✅ `enrichment/` ← seniority_classifier, quality_classifier, match_insights, rescorer, highlighter | ✅ repointed (core, search orch, chat, search bp, saved bp) | ✅ DONE: 2a moved; rescorer/highlighter/seniority/quality → SO (prompts+schemas in `config.py`, `shared.get_client`); match_insights verified no-LLM. 26 offline + 4 live smoke. All `parse_json`/`json.loads`/own-clients gone. |
| 3 | ✅ `interview/` ← interview_helper | ✅ interview bp repointed | ✅ DONE: file → package (`orchestrator.py` + `config.py`, `__init__` API); all 8 model calls → SO (prompts+schemas in `config.py`, `shared.get_client`); `_parse_json` gone; "ONLY JSON" boilerplate gone. 18 offline + 2 live smoke. |
| 4 | ✅ `reporting/` ← report_generator, report_pipeline, opportunity_briefing | ✅ analytics/saved/radar bps repointed | ✅ DONE: package (`__init__` API + `config.py`); 3 calls → SO (opportunity_briefing `generate_briefing`/`suggest_filters`, report_generator `elaborate_items` — was `chat.completions`+JSON array); own clients/`json.loads`/fence-strip gone, prompts+schemas in `config.py`; report_pipeline verified pure PDF (no LLM). 12 offline + 3 live smoke. |
| 5 | ✅ chat distributed (see DECISION) — **job-search chat DELETED** (superseded; UI already gone), **single-job chat → `services/search/job_chat.py`** | ✅ chat bp deleted + unregistered; core repointed (job_chat→search, get_client→shared) | **send_message DELETED** not migrated (incl. `_parse`, `enrich_jobs_from_db`+`_apply_row`, `_build_filter_context`); send_job_message text-only move. 4 offline tests. Backend done. Candidate assistant→#7, segment chat→#6. **Dead job-search-chat JS in index.html → removed in 2.4** (interleaved with live code + the shared `jobChatLang` page-lang var; safe only with in-app verification). |
| 6 | ✅ `clustering/` ← clustering(→embeddings+segmenting), persona, **+ segment_chat** | ✅ cluster bp repointed (package API + segment chat) | ✅ DONE: package (`__init__` API + `config.py`); **persona** `_parse_json_obj`→SO (`PersonaResult`, member fallback kept); embeddings→`shared.get_client` (no parse); segmenting pure scipy; segment chat text-only moved from chat.py. 10 offline + 3 live smoke. |
| 7 | ✅ `candidate/` ← candidate_store(→store), example_cv, profile_enricher, **+ assistant** | ✅ candidate bp (example_cv/enricher), saved/guided/cluster bp (store), core (assistant) | ✅ DONE: package (`__init__` API + `config.py`); **profile_enricher** `_parse_json`+own-client→SO (`LinkedInProfile` 18-field, merge-over-base kept); **assistant** `_parse_candidate`→SO (`CandidateReply` + explicit-field `ProfileUpdates`, nullable nested = pure-discussion); store=DB-only, example_cv=pure PDF. **chat.py DELETED** (last surface left). 12 offline + 3 live smoke. |
| 8 | ✅ `geo/` ← at_geo | ✅ report_pipeline repointed | ✅ DONE: package (`__init__` API + `config.py` re-exporting HAS_MAP); pure polygon data, no LLM/DB. 3 offline tests. |
| 9 | ✅ `auth/` ← auth(→accounts) | ✅ app.py import path unchanged (package exports same names) | ✅ DONE: package (`__init__` API + `config.py` = APP_SCHEMA + SEED_USERS); DB only, no LLM. 3 offline tests (verify_login). |

> **DECISION (amends the old "one `chat/` module"): chat is distributed by DOMAIN, not
> kept as a feature.** Today's top-level `chat.py` is a junk-drawer — four independent
> functions (no shared class/state) colocated only because they all call the Responses API.
> Three of the four belong with the domain data they operate on, so they move there instead
> of into a catch-all `chat/`:
> - **candidate assistant** (`send_candidate_message` + `_parse_candidate`) → `services/candidate/` (#7)
> - **segment chat** (`send_segment_message`) → `services/clustering/` (#6)
> - **job-search chat** (`send_message`, conversational `file_search`) **+ single-job chat**
>   (`send_job_message`) **+ `enrich_jobs_from_db`** → `services/chat/` (#5) — these two are
>   genuinely the *jobs* domain's conversational layer, so `chat/` now means ONE coherent
>   thing (talk to / about jobs), not a grab-bag.
>
> Each surface's SO conversion + tests ride with ITS step (candidate assistant in #7, etc.),
> so they're no longer all in #5. The `_LANG_INSTRUCTIONS` map + the `previous_response_id`
> session pattern are the only shared *mechanism*; factor the session helper into `shared/`
> only if a second domain genuinely needs it (don't pre-abstract). Top-level `chat.py` stays
> a re-export shim until the last surface leaves, then is deleted (≤ 2.5).

**2.4 frontend** also carries `SO →`: the blueprint-level model calls convert during the
frontend repackaging — every LLM call moves to `responses.parse(text_format=PydanticModel)`
on the shared `get_client`, gets relocated into a service module, and the blueprint thins to
parse→call→jsonify. Same rule: convert + delete any hand-parser + two test layers.

- **Legacy hand-parsed JSON sites** (the old "respond with ONLY JSON" + `json.loads`/regex
  pattern) → a real multi-field schema: ✅ `candidate` parse-profile (`CandidateProfile`, #2),
  ✅ `cluster` (`parse_json`, #5), ✅ `saved` (`ObservationOverrides`, #7), ✅ `job_detail`
  (candidate-strength → `CandidateStrength`; its other 4 calls were prose → `JobDetailText`, #8).
  The `job_detail` strength call was the **last** such hand-parse in a blueprint. (The `search` bp
  turned out to have no real-JSON site — its one inline call, match-analysis, is prose → `MatchAnalysis`, #9.)
- **Prose calls** (`analytics` chat, `radar` chat, `company` summary; the 4 `job_detail` text
  tools; `search` match-analysis) → still `responses.parse`, but with a **single-field** model
  (e.g. `AdvisorReply.answer`, `JobDetailText.text`, `MatchAnalysis.text`) since the output is prose.
  These were mis-labeled "beg-for-JSON" in an earlier draft; they never returned JSON. The
  point of converting them is to kill the last raw `OpenAI()` + `chat.completions` holdouts
  and thin the blueprints, not to invent a fake schema.

**2.4 — Frontend** (`web/` → `frontend/`)
- Rename `web/` → `frontend/`. Update `web/__init__` registry, `app.py`, top-level
  `__main__.py`, and **`pyproject.toml`**: `[project.scripts]` `…web.app:main` →
  `…frontend.app:main`, package-data `web/templates/*.html` → `frontend/templates/*.html`;
  then `pip install -e .` to refresh the entry point. Thin blueprints to call service public
  APIs. Add `frontend/integration_tests/` (Flask `test_client`). Gate: `boot` + console
  script + `tab` + integration tests.
- **Remove the dead job-search-chat JS** (left from 2.3 #5, whose backend + `/api/chat` are
  already gone): in `index.html`, `runChatQualityCheck` (~8019–8100) and the `sendChat`
  cluster (`8319–8638`: vars `chatLastJobs`/`chatIsWaiting`/`chatInited`, `initChat`,
  `quickAsk`, `sendChat`, `appendUserMessage`, `appendAiMessage`, `guessSeniority` +
  seniority-chip helpers, `loadChatJobs`, the chat-filter helpers, `newChat`, `scrollChat`,
  the two listeners), plus simplify line ~7739 (`job._batch === 'chat' ? chatLastJobs :
  lastResults` → `lastResults`). **Keep** `jobChatLang` (the page-wide AI-lang var used by
  job chat / guided / interview). Verify the search/interview/guided tabs still work in-app.

**2.5 — Dissolve `core/` + remove shims** ✅ **DONE** *(decision: dissolve the facade)*
- ✅ Repointed the 5 `from …core import` sites (search, job_detail, candidate ×2, guided) to the
  service packages' own APIs — `candidate`/`enrichment` via package `__init__`; `search` symbols
  (Orchestrator, analyze_candidate_match, send_job_message/clear_job_session) via submodule, since
  `search/__init__` is intentionally export-free. Deleted `core/`.
- ✅ Audit correction: the "shims" this step expected to remove **didn't exist** — chat remnants were
  already gone (#5/#7), and 2.1c/d/e had never run, so `search/utils` was real code, not a delegation,
  and `taxonomy.py` was the real module. So 2.5 absorbed the deferred **2.1d** (`grade`→`shared/grading`,
  removing the search→enrichment sideways import — the one real §3 violation) and **2.1e**
  (`taxonomy`→`shared/taxonomy`), and formally **dropped 2.1c** (`shared/job` no longer justified).
  Cleaned the stale `TODO(rework 2.1d)` in `config/settings.py`.
- Gate: ✅ `boot` (create_app, 74 url rules) + `pytest -m "not smoke"` = **182 passed, 31 deselected**
  (unchanged from the 2.4 baseline → behavior-preserving). Smoke + in-app `tab` not re-run (no model/DB
  path changed — only import locations).
- **Shims remaining after 2.5: none.** `shared/` is now `llm` + `grading` + `taxonomy` (no `json`, no `job`).

**2.6 — Frontend internal modularization** (the symmetric half of the front/back split — see §12)
*Stages 2.1–2.5 modularized the **backend**; the API seam is clean but the **client** is still
one 10,754-line `index.html` (≈1,400 CSS / ≈650 HTML / ≈8,300 JS in a single global `<script>`,
88 inline `fetch()`, 197 inline `onclick=`). 2.6 gives the frontend the same low-coupling /
high-cohesion treatment.* Asset/module strategy **DECIDED: native ES modules** (§12).
The cuts, lowest-risk first, each its own commit and **leaving the app working** (verify in-app
per the workflow we just used — login, reload, console clean, tabs exercised):
- 2.6a ✅ **DONE** Extracted the 3 non-Jinja `<style>` blocks → `frontend/static/css/` (`app.css` 1085 /
  `saved-dashboard.css` 287 / `feedback.css` 16 lines), linked via `url_for('static', …)`; kept the 4 Jinja
  feature-flag toggles inline. Added `frontend/static/css/*.css` to pyproject package-data. index.html
  **10,754 → 9,364 lines**. Verified in-app: all 3 sheets load + parse (978/262/16 rules), computed styles
  correct (feedback btn, body theme, tabs), console clean, page renders.
- 2.6b ✅ **DONE** **Extract a thin API client** — collapsed the `fetch()` calls behind one module.
  - ✅ Infra: `static/js/api.js` (ES module) with the protocol core — `get(path)` / `post(path,body)`
    (parsed `{ok,error}` envelope, throws on `!ok`) / `raw(path,opts)` (Response, for SSE streams + blob
    downloads). Module bridge in `<head>` assigns `window.api` for the not-yet-modularized inline script;
    bare `loadFilters()` init deferred to `DOMContentLoaded` (only parse-time API caller — audited) so it
    runs after the deferred bridge. Added `static/js/*.js` to package-data.
    api.js grew `patch`/`del` (envelope) alongside `get`/`post`/`raw`.
  - ✅ Migrated **79 of 88 sites** across 9 commits: part 1 search (b71f8ba), part 2 saved (5c6b59b),
    part 3 rest of throw-sites (3a522fa), part 4 cluster/multi-CV (1f1b704), part 5 extras-picker+save (7a3d6d5),
    part 6 interview (5dfe646), part 7 candidate-assistant+multi-CV match (28ea981), part 8 saved
    lookups/observation/report+example blob (6f2019c), part 9 job_chat / opportunity chats /
    filter-assist / analytics-report blob / candidate_strength / saved POSTs / desc_outreach.
    **Decision (throw+surface):** inline-`data.ok` sites convert to `api.*` and let errors throw; the existing
    catch surfaces them (kills the silent error-swallowing). Verified live: filters/radar/saved/company/cluster
    flow through `api.*`, console clean, boot OK; node --check + Jinja compile after every batch.
  - **9 sites stay raw `fetch` by design:** 4 FormData uploads (parse-pdf ×3, interview/extract) + 1 blob
    fetch (`item.pdf`) — the JSON envelope client can't carry them; and 3 graceful-degradation reads
    (the two best-effort `loadSaved` dual-loads + `salary_stats`, which fall back inline on `!ok` rather
    than throwing). Documented at their call sites.
  **NOTE (2026-06-25): 2.6d runs BEFORE 2.6c.** The split into ES modules is blocked by the
  HTML→global coupling: module scope is not global, so 197 `onclick=` + 29 other inline handlers
  (136 distinct functions) would each need a temporary `window.fn = fn` bridge. Removing the inline
  handlers first — while everything is still one global script and the functions are trivially
  reachable — eliminates that coupling, so the module split lands clean with no scaffold.
- 2.6d **Replace inline `onclick=` with event listeners** (delegation / `data-action`), so markup
  stops referencing globals by name — kills the HTML→global-fn coupling that made the dead-code sweep hard.
  ✅ **COMPLETE (226/226 — zero inline handlers remain in `index.html`).** Mechanism: five delegated
  listeners on `document` (`click`/`input`/`change`/`keydown`/`focusout`) read `data-[*-]action="name"`
  and look the handler up in a single `_ACTIONS` registry; each feature registers its handlers (reading
  params from `data-*`) in a co-located `Object.assign(_ACTIONS,{…})` block next to its own code, so the
  maps split cleanly with the modules in 2.6c. Dynamic args (`${id}`) → `data-*`; `this` → `el`; inline-JS
  (`stopPropagation`/`preventDefault`/backdrop `event.target===this`) preserved inside the registered handler.
  - ✅ part 1 (pilot): dispatcher core + `_ACTIONS` registry; job-chat lang buttons (3).
  - ✅ part 2: `input`/`keydown` listeners; whole Multiple-CV cluster feature (23).
  - ✅ part 3: `change` listener; Radar/Analytics static markup (25).
  - ✅ part 4: job-detail modal static markup (40).
  - ✅ part 5: search-tab static markup (39); added `focusout` listener for the one `onblur`.
  - ✅ part 6: saved + radar static stragglers (22) — clears ALL static-HTML handlers.
  - ✅ part 7: search-region JS template-string handlers (guided fields/chips, results rows, cand-asst
    chips, extras picker, candidate card).
  - ✅ part 8 (FINAL): radar/analytics chips + summary, interview scorecard, feedback widget; dropped a
    dead `href="#" onclick="return false"` placeholder. Per-batch gate each time: 0 inline attrs in the
    batch region, every `data-*action` cross-checked to an `_ACTIONS` key, `node --check` on rendered
    inline JS, Jinja compile, `create_app` boot (GET / → 302). NOTE: verification was static-only
    (`/` redirects to login) — an interactive pass (login + click each tab) is still worth doing.
- 2.6e ✅ **DONE — Frontend test harness — Playwright E2E smoke** *(prerequisite for 2.6c)*.
  Built `tests/jobs_intelligence_ai/frontend/e2e/` (`conftest.py` + `test_tabs_smoke.py`): live
  in-process Werkzeug server with auth stubbed (no MySQL — real form login vs. a fake admin) and all
  country flags forced on; logs in once, drives the real nav (Candidate/Analytics mode toggle →
  search/saved + radar/map/analytics-summary), asserts each tab goes `active` and `pageerror` stays
  empty. `e2e` marker registered; opt-in via `-m e2e`; offline gate is now
  `pytest -m "not smoke and not e2e"`; deps in the `test` extra (`pip install -e .[test]` +
  `playwright install chromium`). **Confirmed: chromium launches headless in the dev sandbox**, so the
  split is verifiable here, not just in CI. **On first run it caught a real latent bug** — `_ACTIONS`
  declared in its temporal dead zone (registration blocks ran before the `const`), which had silently
  broken the whole script since 2.6d part 2 and passed all 8 static-only gates. Fixed (hoisted the
  declaration). This is the exact class of failure 2.6c risks — now caught automatically.

  Original rationale (kept for context):
  **Why:** today's `frontend/integration_tests/` use Flask `test_client`, which **never executes the
  client JS** — it only checks server responses. So nothing tests the actual 8,300-line script; a broken
  cross-module `import` in 2.6c would be invisible to `node --check` + boot-302 and only surface when a
  human clicks the tab. A real (headless) browser closes that gap, and it can be **run from the terminal**
  (no manual app-opening) — so the split becomes verifiable per-module instead of blind.
  - Tool: **`pytest-playwright`** (fits the existing pytest stack; sits next to `integration_tests/`).
    Setup: `pip install pytest-playwright` + `playwright install chromium` (no Node project needed).
  - Pieces: ① **auth fixture** — log in once via `SEED_USERS`, save `storage_state` (session cookie),
    reuse across tests (handles the login gate one time). ② **tabs-smoke test** (the high-value one) —
    for each tab: click `[data-tab="X"]`, assert `#tab-X` visible AND **zero `console` errors**; this
    catches the exact 2.6c failure mode (missing import → ReferenceError on tab click). The `data-action`
    attributes from 2.6d give stable selectors. ③ later: a few flow tests (run a search with the backend
    mocked, open a job modal). Make tab-loads deterministic by mocking the on-open fetches (Playwright
    `route`) or filtering network errors from JS errors.
  - Gate: the smoke suite goes **green on the CURRENT (pre-split) app** first — that's the safety net.
  - Caveat: confirm a headless browser can launch in the dev sandbox; if not, the suite still runs in the
    normal env / CI (one command vs. manual clicking).

- 2.6c **Split JS into per-feature ES modules** (Phase 1 — *pure move, behavior-preserving*). ✅ **DONE**
  — all 16 modules extracted one-per-commit; final module `boot.js` (`346097d`) swapped the inline
  `<script type="module">` for `<script src=".../boot.js">` and removed the `window.api` head bridge, so
  `index.html` is now pure markup with zero inline JS. Boot-302 green. ⚠️ Owes one interactive click-test
  (login + drive every tab/modal) before merging to `master` — static gates can't prove the page boots.
  - ✅ step 0 (`04e2f7b`): flipped the page `<script>` → `<script type="module">`. Pure scope flip; safe
    because 2.6d removed all inline handlers (recon: script reads only CDN globals `L`/`Plotly`/`XLSX` +
    `window.api`, exports nothing to window, no top-level `this`). Smoke green = HTML→global coupling
    fully gone, no `window.fn` bridge needed.
  - ✅ module 1/13 `map.js` (`8b09185`): proof-of-shape. **Proven mechanism** the rest follow:
    (1) move the section's funcs + private vars into `static/js/<feat>.js`, `export` them; (2) at the top
    of the page module, `import { … } from "{{ url_for('static', filename='js/<feat>.js') }}"`;
    (3) a cross-module data read becomes a **handoff** — pass it as an arg (e.g. `initMap(lastResults)`),
    don't import a shared global; (4) gate: e2e smoke (clicks the tab → loads the module) + module-aware
    `node --check` (write extracted inline JS to a `.mjs`, since top-level `import` needs ESM) + boot-302
    + offline suite. One module per commit.
  - ✅ module 2/13 `export.js` (`7f7c761`): CSV/XLSX/PDF. `XLSX` = CDN global; `api` now imported
    explicitly (`import api from "./api.js"`) — the direction new modules go (window.api bridge retires
    once the page module stops using bare `api`). Handoffs: results / savedJobs / `_miCandidates[_miIdx]`.
  - ✅ module 3/13 `util.js` (`eefecb3`): **shared layer, pulled forward out of size order** — feature
    modules call `esc` (used 204×) / `mdToHtml`, and a static module can't import from the inline page
    script, so the shared helpers must exist first. Also owns the job store (`storeJob` + new
    `getStoredJob`; `_jobStore` Map private). **Registration pattern decided:** `_ACTIONS` stays in the
    page module; feature modules just `export` their handler functions and the existing `Object.assign`
    blocks reference the imported bindings — so `_ACTIONS` never needs to move (consolidates into boot last).
  - ✅ module 4/13 `state.js` (`f353ccb`): keystone — `export const state = {filterOpts:…}` (shared
    singletons as object properties so modules can mutate) + `export const _ACTIONS = {}` (so feature
    modules keep co-located registration blocks by importing it). `_filterOpts`→`state.filterOpts`.
  - ✅ module 5/13 `radar.js` (`f64abbc`, 1217 lines): first big feature module. Only coupling was
    `_filterOpts` (→ state); only `loadRadar` called externally. Spliced the whole section (41 fns + its
    own `_ACTIONS` blocks) via Python regex; prepend import header, `export loadRadar`, placeholder left.
  - ✅ shared-state migration (`63cdb4b`): the 5 cross-cutting singletons → `state.*`
    (`lastResults`/`modalJob`/`activeMode`/`currentCandidateProfile`/`savedJobs`). Cross-module *state* solved.
  - ✅ smoke strengthened (`e1509d8`): `e2e/test_search_modal.py` runs a real search (mock `/api/match`) +
    opens the modal — and on first run caught a real bug the migration introduced (a local `const state`
    shadowing the import in runMatching/findMoreJobs; fixed → `stateF`). Two e2e tests now: tabs + search→modal.
  - ✅ **remaining 8 = ONE mutually-referential CORE CLUSTER** (search, candidate, saved, modal, interview,
    clustering, assistant, guided) + boot. NOT peelable in pairs. **EXECUTION SPEC (measured):** the raw
    cross-module surface looked huge but separates into 3 buckets:
    1. **Shared state (~18 vars)** → move to `state.js` (continue the `lastResults` pattern). These inflate
       the "exports" but are variables, not API. Migrate FIRST — it removes most coupling and is the only
       part that's safely incremental.
    2. **`data-action` registrations (+36 "exports")** → NOISE. They look cross-module only because a
       handler's registration currently sits in a neighbour's region. Keep each registration co-located with
       its function (move it with the module) and the edge vanishes. Zero work.
    3. **Genuine function API = 26 exports total**, small per module: candidate 8, search 7, saved 4,
       interview 3, assistant 2, clustering 1, guided 1, **modal 0** (its 11 "exports" were all state).
       Plus pure helpers in the wrong place (e.g. `gradeClass`) → move to `util.js`, removing the edge.
    **Order:** (i) finish state→`state.js`; (ii) move stray pure helpers to `util.js`; (iii) then the 8
    files. Because every core module calls ≥1 other (search↔candidate↔saved↔modal↔interview…), step (iii)
    is irreducibly **coordinated** — extract the cluster together with circular imports (valid in ESM, calls
    fire at runtime), OR route cross-module calls through a late-bound registry (like `_ACTIONS`) to keep it
    one-module-per-commit. Gate per file: node --check + identifier-resolution (called idents − local −
    imports − globals = ∅) + both e2e smokes + boot-302.
  Cut the one inline `<script>` into the files below (sizes = real line counts from the split), add
  `import`/`export` only for cross-file refs, and replace the inline block with
  `<script type="module" src="…/boot.js">`. **No logic changes** — a missed reuse/cleanup waits for 2.6f.
  Proposed `static/js/` layout (mirrors the backend: `boot.js`≈`app.py`, `util.js`/`state.js`≈`shared/`,
  each tab file ≈ a `services/` module):

  | file | ~lines | covers |
  |---|---|---|
  | `api.js` | 60 | (exists) fetch wrappers |
  | `util.js` | 110 | `esc()`, formatters, the `_ACTIONS` dispatcher, job store, session id |
  | `state.js` | 40 | the few genuine cross-module singletons (current candidate, active mode) |
  | `candidate.js` | 1300 | input modes, CV upload/parse, profile card, LinkedIn, examples |
  | `guided.js` | 290 | guided "build a template" chat |
  | `assistant.js` | 395 | docked candidate-assistant chat |
  | `clustering.js` | 650 | Multiple-CV → talent segments |
  | `search.js` | 780 | run matching, SSE progress, render/sort/save/freeze, row actions, extras |
  | `saved.js` | 1240 | the saved candidates/jobs panel (table + dashboard) |
  | `modal.js` | 970 | job-detail modal + quality + sub-chat + analysis panels + translate |
  | `interview.js` | 930 | interview scorecard |
  | `radar.js` | 1220 | radar/analytics + AI filter assistant + opportunity cards |
  | `map.js` | 50 | the Leaflet map tab |
  | `export.js` | 155 | CSV/Excel export |
  | `boot.js` | 120 | tab routing, init, feedback widget, registers all `_ACTIONS`, DOMContentLoaded |

  **Shared-state rule (decided):** of the 149 top-level vars, ~113 are used 1–8× inside one feature →
  they just become **module-private** on the move (no accessors — the split *fixes* them for free). Of the
  ~36 cross-section vars, most are also module-internal once the boundary wraps the whole feature *cluster*
  (e.g. modal+quality+interview+analysis = one module), or are a **handoff** → pass as a function argument
  (`openJobModal(job)`, not a shared global). Only a single-digit residue of genuine read-many singletons
  (e.g. current candidate profile, active mode) live in `state.js` and get a plain **getter** (setter only
  where the write has a side effect, e.g. "candidate changed → mark scores stale"). **No blanket
  getter/setter ceremony.**
  - Order: smallest/safest first (`map.js`) as a proof-of-shape, then up to the big ones
    (`saved`/`radar`/`candidate`). **One module per commit** so a break is isolated.
  - Gate per module: 2.6e **smoke green** (run the headless browser — click every tab, console clean) +
    `node --check` + Jinja compile + boot-302 + `integration_tests` still green. Smoke is the one that
    actually proves a cross-module import didn't break.

- 2.6f **Simplify each module** (Phase 2 — *behavior may change; separate commits, AFTER 2.6c is committed*).
  Rule: **never mix a move with a rewrite** — so this is its own pass once the split is stable and the diff
  per file is small/reviewable. Per file: delete dead code, dedupe, and **sub-split the oversized ones**
  (`candidate.js` 1300 / `radar.js` 1220 / `saved.js` 1240 are doing several jobs each). Gate per change:
  the 2.6e smoke + any added flow tests must stay green (this phase is exactly where click-testing is
  non-negotiable, now automated).
  - ✅ **DESCOPED / CLOSED (2026-06-29).** One clean sub-split landed: `candidate-examples.js` extracted
    from `candidate.js` (1420→892 lines, `a64d770`) — the bundled demo-candidate data + Examples dropdown,
    a true leaf. `radar.js` and `saved.js` were assessed and **consciously dropped**: they're cohesive tab
    modules with no clean leaf seam (`loadRadar` drives analytics+finder+trend through shared module state
    + one `_ACTIONS` block; `saved.js`'s `_mi*` dashboard / table / `_ic*` chat are physically interleaved).
    Splitting them needs shared-state migration whose only safety net is the 2.6e click-test — not worth the
    risk/time as polish. Revisit only if those files actively get in the way, and only with the e2e smoke on.
  - Latent bug surfaced during the split (out of scope, separate task): `{{ country_code }}` /
    `{{ country_demonym }}` in the **static** JS (`candidate-examples.js`, `radar.js`) never render — Flask
    serves `static/` raw — so the SK example set + radar demonym are broken since 2.6c pulled them out of the
    Jinja-rendered inline script. Fix = inject country into the JS from the rendered `index.html`.

**Stage 2.6 — ✅ CLOSED (2026-06-29):** 2.6a–2.6e done; 2.6c done (full ES-module split); 2.6f descoped to
the one safe sub-split. Frontend is now CSS + thin `api.js` + per-feature ES modules + pure-markup
`index.html`. Remaining owed item before `master`: the interactive click-test of the split (Stage 3 gate).

Gate per step: 2.6e smoke (all five tabs, console-clean) + `boot` + `integration_tests` green.

- [ ] **Stage 3 — Make `master` the lean app.** Bring only matured modules onto `master`
      (search + whatever basics we bless — deferred), replacing the old `demo_real/` content. Push.
      Also in scope for Stage 3 (product, not just plumbing):
      - **Rebrand to Acme Recruitment** — apply Acme Recruitment coloring/theme across the
        UI (the CSS we extracted in 2.6a is the seam for this). Palette + assets TBD.
      - **Expand candidate-search filters** — add more filter dimensions to the candidate search.
        Specific fields TBD.

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
- `config.py` = **always present** — the module's settings as flat constants (Level 2, §5):
  model, prompts, thresholds, flags, and its Structured-Outputs Pydantic schemas. Even a
  pure/small service gets one, so each module has a single, predictable home for its knobs.
- `__main__.py` = standalone runner **where running alone is meaningful**
  (search, clustering: yes; auth: optional smoke test). Not dogmatic.
- Helpers split by job; the blueprint shrinks to: parse request → call
  orchestrator → jsonify, and lives in `frontend/`.

---

## 8. Current → target file map (full)

| Today | Target |
|---|---|
| `chat.py` → `get_client` | `shared/llm.py` (done 2.1a) |
| `chat.py` → send_message/_parse, enrich_jobs_from_db | **DELETED** (superseded; #5) |
| `chat.py` → send_job_message | `services/search/job_chat.py` (#5) |
| `chat.py` → send_candidate_message/_parse_candidate | `services/candidate/assistant.py` (#7) |
| `chat.py` → send_segment_message | `services/clustering/segment_chat.py` (#6) |
| `chat.py` (file) | **DELETED** at #7 — fully dissolved |
| `taxonomy.py` | `shared/taxonomy.py` |
| `search/utils.py` → grade | `shared/grading.py` (2.5). parse_json + serialize_job **STAY** in `search/utils.py` (no `shared/json.py`/`shared/job.py` — see §4) |
| `core/` (facade re-exporting chat/search/services) | **dissolved** — each service `__init__` is its own public API |
| `config/` | `config/` = environment layer; matching tunables move OUT to `services/search/config.py` (§5) |
| `infra/`, `integrations/linkedin.py` | `infra/` + `infra/integrations/linkedin.py` ✅ (2.5 follow-up; candidate bp repointed) |
| `search/` | `services/search/` (move under umbrella — §6 step 2.2a) |
| `services/clustering.py` + `persona.py` | `services/clustering/` |
| `services/interview_helper.py` | `services/interview/` |
| `services/report_generator.py` + `report_pipeline.py` + `opportunity_briefing.py` | `services/reporting/` |
| `services/candidate_store.py` + `example_cv.py` + `profile_enricher.py` | `services/candidate/` |
| `services/seniority_classifier.py` + `quality_classifier.py` + `match_insights.py` + `rescorer.py` + `highlighter.py` | `services/enrichment/` |
| `stats/{opportunity,quality_score,salary_stats}.py` | `services/stats/` |
| `services/at_geo.py` | `services/geo/` ✅ |
| `services/auth.py` | `services/auth/` |
| `web/` (app, blueprints, templates) | `frontend/` |

Note: `python -m jobs_intelligence_ai.search` becomes `…services.search` after 2.2a.

---

## 9. Decisions log

- ✅ Branch model: TWO branches — `master` (stable, the base) + `develop` (everything, on top). No separate `production`.
- ✅ Three-layer architecture (foundation / services / frontend).
- ✅ Services-module pattern (§7).
- ✅ `tests/` + `documentation/` stay at **repo root** as siblings of `src/`, mirroring the package (matches Work convention; already true today). Not nested in `src/`.
- ✅ `shared/` (§4): **as built = `llm` + `grading` + `taxonomy`** (`job` dropped — single-domain after `_apply_row` deletion; `json` superseded by Structured Outputs). Unifies the 2 OpenAI client paths + the cross-service `grade()`.
- ✅ **Structured Outputs (2.1b)**: JSON-returning model calls use `responses.parse(text_format=Pydantic)` → `output_parsed`. Deletes the 3 JSON parsers (no `shared/json.py`). Verified vs official docs + live SDK 2.30.0. `pydantic` added to deps. ✅ file_search + structured outputs confirmed to coexist (probed live in 2.2c) — chat #4 unblocked (needs prompt tuning, not an API change).
- ✅ Config (§5): flat module constants per service; global = environment/identity layer (not aggregator); move matching tunables into `services/search/config.py`. Dataclasses dropped.
- ✅ Execution plan (§6): ordered, commit-per-step, shim-based, verify after each. Test scaffold (2.0) goes first.
- ✅ Testing (§10): full coverage scope — mirrored test tree, **a test package per service** (mirrors the API principle), unit tests with `_fake_db` + mocked `shared/llm` client; fake-DB now, docker integration later.
- ✅ Documentation (§11): `documentation/` mirrors the package, one folder per module (`Work` convention); docs realigned to the target structure; `TESTING.md` added.
- ✅ `search/` moves under `services/search/` (2.2a).
- ✅ `core/` facade dissolved into per-service `__init__` APIs (2.5 — DONE). 2.5 also absorbed the
  never-run 2.1d (`grade`→`shared/grading`, fixing the search→enrichment sideways import) + 2.1e
  (`taxonomy`→`shared/taxonomy`), and **dropped 2.1c `shared/job.py`** (single-domain after `_apply_row`
  deletion). Final `shared/` = llm+grading+taxonomy; zero shims remain. Gate: 182 passed, boot OK.
- ✅ `geo` + `auth` as their own `services/` modules.
- ✅ **Chat distributed by domain** (amends "one `chat/` module", 2026-06-23): `chat.py` is a junk-drawer of 4 independent Responses-API functions; 3 move to the domain they serve (candidate assistant→`candidate/` #7, segment chat→`clustering/` #6), and `chat/` keeps only the jobs-domain conversational layer (`send_message` + `send_job_message` + `enrich_jobs_from_db`). Each surface's SO conversion rides with its step. See the DECISION block under §6.
- ✅ **Frontend internal modularization added as Stage 2.6** (2026-06-24): the symmetric half of the front/back split — `index.html` (10,754 lines) breaks into `static/css` + a thin `api.js` client + per-tab JS modules, replacing inline `onclick=` with listeners. Mirrors the backend's "feature = a unit" principle. See §12 + §6 2.6.
- ✅ **Frontend asset/module strategy (§12) — DECIDED (2026-06-24): native ES modules** (`<script type="module">` + import/export, served from `static/`, no bundler/toolchain added to the build-free Flask app).
- ⚠ Production feature set (Stage 3) — mostly deferred, but two items now in scope (2026-06-25):
  Acme Recruitment rebrand (coloring/theme) and expanded candidate-search filters. Specifics TBD.

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
    ├── shared/unit_tests/      # test_3_grading · test_4_taxonomy · test_5_llm
    │                           #   (parse_json/serialize_job tests relocated to search/unit_tests in the
    │                           #   2.5 follow-up — that code stayed in search/utils; job.py/json.py dropped)
    ├── services/
    │   ├── search/{unit_tests,smoke_tests}   # incl. test_parse_json, test_serialize_job, test_job_chat
    │   ├── stats/ enrichment/ interview/ reporting/ clustering/ candidate/ job_detail/ geo/ auth/
    │   │        └── unit_tests/ (+ smoke_tests where live)   # one test package per service
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

---

## 12. Frontend modularization (Stage 2.6) — design + decision (native ES modules)

**Why.** The backend rework (2.1–2.5) made "frontend vs backend" true at the *process*
boundary: thin blueprints, clean JSON API, services that never import the frontend. But it
is **not** true *inside* the frontend. [index.html](../../../src/jobs_intelligence_ai/frontend/templates/index.html)
is one file fusing four concerns:

| Region | ~Lines |
|---|---|
| CSS (`<style>`) | ~1,400 |
| HTML markup | ~650 |
| JS (one global `<script>`) | ~8,300 |

with **88 inline `fetch()`** (every feature hand-rolls its endpoint string + `{ok,error}`
unwrap) and **197 inline `onclick=`** (markup wired to global JS functions *by name* — the exact
coupling that forced the painstaking identifier sweep in the dead-job-search-chat cleanup). Low
coupling at the API ≠ low coupling across the whole design; 2.6 closes that gap.

**Target shape** (mirrors the backend's "feature = a unit, not scattered" principle):
```
frontend/
├── static/
│   ├── css/            # extracted styles (2.6a)
│   └── js/
│       ├── api.js      # ONE thin client over the 88 fetch() calls (2.6b)
│       ├── boot.js     # app init, tab wiring, shared state
│       ├── util.js     # shared helpers (formatting, DOM)
│       └── tabs/       # search.js · saved.js · radar.js · map.js · analytics.js (2.6c)
└── templates/
    └── index.html      # markup + Jinja only; data-action hooks, no inline JS (2.6d)
```

**✅ DECIDED — native ES modules** (option 2 below). `<script type="module">` + `import`/`export`,
served from `frontend/static/`; no bundler. `pyproject.toml` package-data grows to ship `static/`.
Today the app is pure Flask + three CDN `<script>` tags (leaflet/plotly/xlsx); **no `static/` dir,
no JS build tooling**. The three options that were on the table, in ascending toolchain cost:

1. **Plain multi-file `<script src>`** — global namespace, load-order-dependent. Zero tooling;
   smallest change, but keeps the global-soup coupling (just spread across files).
2. **Native ES modules (`<script type="module">` + `import`)** — real module boundaries, no
   bundler (modern browsers do it natively), Flask just serves the files. *Recommended:* the
   sweet spot — true decoupling, no toolchain added to a demo app.
3. **Bundler (Vite/esbuild)** — best DX/minification, but introduces a build step + `node_modules`
   to a currently build-free Python app. Likely overkill for the demo phase.

Chose **(2)**: it gives real module boundaries with zero toolchain added to the build-free app, and
sets how `api.js`/tab modules reference each other (native `import`). `pyproject.toml` package-data
must grow to ship `static/`.

**Sequencing note.** 2.6 is independent of 2.5 (backend shim removal) and could run in parallel,
but the API client (2.6b) is cleanest *after* the API surface stops moving (post-2.4, which is done).
Order within 2.6 is risk-ascending: CSS extract → API client → JS-by-tab → de-inline handlers.
