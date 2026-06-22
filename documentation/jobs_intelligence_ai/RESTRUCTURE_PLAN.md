# Restructure Plan — Modular Rework + Demo/Production Branches

> **Status:** Planning. Direction agreed; **config approach still open** (see §5).
> Nothing in §6 (execution) has run yet except Stage 1 (the `develop` branch).
> This doc is the running record of the rework so we can execute it in steps.

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

## 2. Branch strategy (trunk-based / GitFlow-lite)

| Branch | Role | State |
|---|---|---|
| `develop` | Everything, incl. experimental. Day-to-day work. | **Created + pushed** (commit `c7e52b8`). Holds the full src/ codebase. |
| `production` | Lean, shippable. Only matured features. What we demo. | **Not created yet** — built in Stage 3, after repackaging. |
| `master` | Old `demo_real/` layout. Stale fallback. | Untouched. Fate decided at the end (likely retired/repointed). |

**Workflow:** build on `develop`; when a feature matures, promote *just that
feature* onto `production`.

**The gotcha we're avoiding:** if `production` were just `develop` with files
*deleted*, merging a matured feature later would drag the deleted files back in.
So `production` is the **base** and `develop` adds features *on top*; promotion is
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

## 4. `shared/` — AGREED

Contents derived from the **actual import graph** (only things used by multiple
unrelated callers qualify). Two items are currently in the wrong place and get
promoted:

```
shared/
├── __init__.py
├── llm.py        ◄ get_client() OpenAI client factory   (FROM: chat.py, top-level)
├── json.py       ◄ parse_json() — strip fences, parse    (FROM: search/utils.py)
├── grading.py    ◄ grade() + score→A/B/C banding          (FROM: search/utils.py)
└── taxonomy.py   ◄ sector/role taxonomy for the funnel     (FROM: taxonomy.py, top-level)
```

| Promoted file | Independent callers today |
|---|---|
| `llm.py`  (was `chat.py`)            | clustering, persona, chat/guided |
| `json.py` (was `search/utils.py`)    | search, highlighter, rescorer |
| `grading.py` (was `search/utils.py`) | search, rescorer |
| `taxonomy.py` (top-level)            | guided funnel, search/stats |

**Sign-off needed before this touches code:** pulling `parse_json`/`grade` out of
`search/` and `chat.py`→`shared/llm.py` means updating imports in `search` and a
couple of services. User has seen this; flagged as the one change to working code.
→ **APPROVED in principle** (direction agreed); apply during Stage 2.

`config/` and `infra/` stay as **sibling foundation packages** next to `shared/`
(distinct concerns: settings vs I/O vs reusable code).

---

## 5. Config — ⚠ OPEN / NOT YET AGREED

> User agrees with the overall direction and with the services-module pattern (§7),
> but **does not yet fully agree with the config approach below.** Treat this
> section as a proposal to revisit, not a decision.

**Proposal on the table (two levels):**

- **Level 1 — global** (`config/settings.py`, exists): country profile, API keys,
  DB URL, model names, Flask. App-wide.
- **Level 2 — per-service** (`search/config.py`, exists — the `company_match/config.py`
  analog): the service's own tunables as dataclasses, defaulting from global config
  but overridable per call. Rule: *global = "what app/country am I?"; per-service =
  "how does this feature behave?"*

**Status:** revisit and resolve before Stage 2 packaging of non-search services.
_Open questions to settle: <to be filled from next discussion>._

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
- [ ] **Stage 3 — Create `production`.** Branch from `develop`; include only matured
      modules (search + whatever basics we bless — deferred, not chosen yet). Push.
- [ ] **Stage 4 — Retire/repoint `master`** once `production` is the trunk.

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

- ✅ Branch model: trunk-based, `production` is base, `develop` adds on top.
- ✅ Three-layer architecture (foundation / services / frontend).
- ✅ `shared/` contents and the two promotions (§4).
- ✅ Services-module pattern (§7).
- ⚠ **Config approach (§5) — OPEN.**
- ⚠ Production feature set (Stage 3) — deferred, not chosen.
- ⚠ `search/` placement (top-level vs under `services/`) — to confirm.
- ⚠ `geo` / `auth` grouping — to confirm.
