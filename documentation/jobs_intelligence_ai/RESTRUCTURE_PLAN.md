# Restructure Plan — Modular Rework + Demo/Production Branches

> **Status:** Planning. Architecture, `shared/` (§4), and config (§5) all agreed.
> **Still open:** execution detail (§6), production feature set, `search/` placement,
> `geo`/`auth` grouping. Nothing in §6 has run yet except Stage 1 (the `develop`
> branch). This doc is the running record of the rework.

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

- [x] **Stage 1 — Safe save.** Commit full current codebase to `develop`, push to
      GitHub. (Done — commit `c7e52b8`, `origin/develop`.)
- [ ] **Stage 2 — Repackage into modules** (on `develop`):
      1. Create `shared/` (§4); update imports in `search` + affected services.
      2. Convert each flat service into a module (§7), one at a time, verifying as we go.
      3. Rename `web/` → `frontend/`; thin out blueprints to call services.
      4. Remove empty `core/`; relocate `taxonomy.py` / `chat.py`.
      5. **Resolve §5 config approach first** for non-search services.
- [ ] **Stage 3 — Make `master` the lean app.** Bring only matured modules onto
      `master` (search + whatever basics we bless — deferred, not chosen yet),
      replacing the old `demo_real/` content. Push.

> **§6 is intentionally coarse — to be expanded.** Stage 2 will be broken into an
> ordered, verifiable sub-sequence (one helper/module at a time, run tests, update
> importers, repeat) so each step is independently checkable and reversible.
> Pending review before execution.

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
| `chat.py` | `shared/llm.py` |
| `taxonomy.py` | `shared/taxonomy.py` |
| `search/utils.py` (parse_json, grade) | `shared/json.py`, `shared/grading.py` |
| `core/` (empty) | removed |
| `config/` | `config/` (unchanged structurally; approach §5 OPEN) |
| `infra/`, `integrations/linkedin.py` | `infra/` (+ `infra/integrations/`) |
| `search/` | `services/search/` (move under umbrella — decision: see note) |
| `services/clustering.py` + `persona.py` | `services/clustering/` |
| `services/interview_helper.py` | `services/interview/` |
| `services/report_generator.py` + `report_pipeline.py` + `opportunity_briefing.py` | `services/reporting/` |
| `services/candidate_store.py` + `example_cv.py` + `profile_enricher.py` | `services/candidate/` |
| `services/seniority_classifier.py` + `quality_classifier.py` + `match_insights.py` + `rescorer.py` + `highlighter.py` | `services/enrichment/` |
| `stats/{opportunity,quality_score,salary_stats}.py` | `services/stats/` |
| `services/at_geo.py` | `services/geo/` (grouping TBD) |
| `services/auth.py` | `services/auth/` |
| `web/` (app, blueprints, templates) | `frontend/` |

**Open decision:** does `search/` move under `services/` for consistency (changes
`python -m jobs_intelligence_ai.search` → `...services.search`), or stay top-level
as the one privileged core? → to confirm.

---

## 9. Decisions log

- ✅ Branch model: TWO branches — `master` (stable, the base) + `develop` (everything, on top). No separate `production`.
- ✅ Three-layer architecture (foundation / services / frontend).
- ✅ Services-module pattern (§7).
- ✅ `tests/` + `documentation/` stay at **repo root** as siblings of `src/`, mirroring the package (matches Work convention; already true today). Not nested in `src/`.
- ✅ `shared/` (§4): `llm` + `json` + `job` + `grading` + `taxonomy`; unifies 2 client paths, 3 JSON parsers, and the duplicated ~30-field job mapping.
- ✅ Config (§5): flat module constants per service; global = environment/identity layer (not aggregator); move matching tunables into `services/search/config.py`. Dataclasses dropped.
- ⚠ Execution detail (§6) — to be expanded into ordered, verifiable sub-steps.
- ⚠ Production feature set (Stage 3) — deferred, not chosen.
- ⚠ `search/` placement (top-level vs under `services/`) — to confirm.
- ⚠ `geo` / `auth` grouping — to confirm.
