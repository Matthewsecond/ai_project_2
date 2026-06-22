# UX / Workflow Cleanup Plan

_Created 2026-06-19. Living doc — update the checkboxes as items land._

## Why

A whole-app workflow review (frontend journey + backend map) found the app has a
**sound engine and good ideas, but feels clunky**. The clunk is **information
architecture and state-awareness, not performance or backend rot.** It currently reads
as *a pile of powerful panels* rather than *one guided funnel*.

### The funnel is fine; the seams are not
The recruiter funnel works stage-by-stage:

```
1 Candidate input → 2 Match → Results → 3 Shortlist/Save → 4 Pipeline + Insights → 5 Interview → 6 Decide
```

Each stage is individually OK. The friction is **what gets lost when you move between
stages** (stale scores, dropped candidate name, lost cluster context) and **how much
depth is buried** (interview scorecard, assistant, clustering).

## Priorities (impact ÷ effort)

| Tier | Theme | User-visible? | Effort |
|------|-------|---------------|--------|
| **P1** | Silent state decay (the seams) | Yes — removes confusing/dangerous moments | Low |
| **P2** | Modal clarity | Yes | Very low |
| **P3** | A primary path through input | Yes | Medium |
| **P4** | Backend hygiene | No (maintainability) | Medium, optional |

All items are in `src/jobs_intelligence_ai/web/templates/index.html` unless noted.

---

## Phase 1 — Kill silent state-decay (P1) · highest ROI · **DO FIRST**

The data to detect these already exists; it just isn't surfaced.

- [x] **1.1 Stale-score warning.** `#staleScoreNotice` banner + `_updateStaleNotice()`
  compares `buildCandidateText()` to `_scoredAgainstText`; shows when frozen + diverged,
  with a one-click **Re-score**. Wired to a delegated `input` listener on `.input-area`,
  `toggleFreeze()`, and cleared after `rescoreFrozenResults()`.
- [x] **1.2 Reset on input-mode switch.** `_resetCandidateOnModeSwitch()` drops the
  derived identity (name tag, profile card, dup warning, `_currentCandidateProfile`) when
  the `.mode-tab` actually changes — **preserves** each zone's typed text (unlike
  `clearCandidateProfile`).
- [x] **1.3 Cluster "← back to segments".** `_mcDrilledFrom` flag + `#backToSegments`
  link (`_mcBackToSegments()` → `setWorkflow('multiple')`, re-renders `_mcLastClusters` if
  needed). Cleared on manual switch to multiple, full clear, and new clustering.

**Verify:** `node --check` on the inline JS; manual — freeze + change candidate shows the
warning; switching modes clears the name; cluster drill-down can return to segments.

---

## Phase 2 — Modal clarity (P2) · tiny, do in the same pass

- [x] **2.1 Active-state on description buttons** — already implemented (the explorer
  read it statically and missed it): Original/Compact via `_syncDescBodyButtons()`,
  CV-Questions/Outreach toggle `.active` + flip to "Hide" inline. No change needed.
- [x] **2.2 Surface the interview scorecard.** Relabeled the button **"CV Questions" →
  "Interview"** (button text, reset block, toggle closed-state, + tooltip). The panel
  header already reads "Interview — scorecard".

**Verify:** open a job, click each description button, confirm active styling; confirm the
scorecard is now discoverable.

---

## Phase 3 — A primary path (P3) · after P1/P2, once we've felt the difference

- [x] **3.1 Separate the single/multi toggle from the input tabs.** The scope toggle is
  now a small labeled control (`.scope-row` → "Looking for" label + compact
  `.workflow-toggle` reading "One candidate / Multiple"), visually demoted so it no longer
  reads as a peer of the method choices. Same `data-workflow` / `setWorkflow()` wiring.
- [x] **3.2 Mark a clear default/primary input mode.** The method row (`.mode-tabs`) is
  restyled from flat chips into three cards (icon-over-label, `flex:1`), with **Search by
  CV** carrying a "Default" badge (`.def-badge`) so a first-timer has one obvious start.
  A `#methodLabel` ("How do you want to add them") heads the row; `setWorkflow()` hides it
  alongside `.mode-tabs` when scope = Multiple. Button `data-mode` / `.active` contract
  unchanged, so all mode-switch logic still works.

---

## Phase 4 — Backend hygiene (P4) · opportunistic / optional · invisible to users

- [x] **4.1 Rename the `/api/saved/interview` collision.** Route + handler renamed to
  `/api/saved/observation` / `api_saved_observation()` in `blueprints/saved.py`; the old
  `/interview` path kept as a stacked `@bp.route` alias (commented for removal). Updated
  the one frontend caller (`index.html` `/api/saved/observation`), the module docstring,
  and the cross-reference note in `blueprints/interview.py`. Both files byte-compile.
  (Audit-log action label left as `interview_update` to avoid breaking log filters.)
- [ ] **4.2 (Defer) Unify the seven `/chat` endpoints** (`chat`, `guided`, `radar`,
  `analytics`, `job_chat`, `cluster`, candidate assistant) behind one shared
  session+prompt helper. Real but larger; only worth it if more chat surfaces are coming.

---

## Recommended sequencing
1. **Phase 1** (kills the dangerous/confusing moments cheaply) → **Phase 2** (same pass).
2. Reassess feel, then **Phase 3**.
3. **Phase 4** opportunistically; 4.2 deferred.

## Out of scope (deliberately not doing now)
- No rewrite. The architecture stays.
- No new framework / component library.
- Backend chat unification (4.2) unless chat surfaces keep multiplying.

## Status log
- 2026-06-19 — Plan written. **Current focus: Phase 1.**
- 2026-06-19 — **Phase 1 implemented** (1.1, 1.2, 1.3) in `index.html`; passes `node --check`.
  Live browser click-through still pending (needs running app + logged-in session).
- 2026-06-19 — **Phase 2 done.** 2.1 already existed (active-state); 2.2 relabel
  "CV Questions" → "Interview". Passes `node --check`. **Next: Phase 3 (primary path) —
  hold per plan until P1/P2 feel is assessed.**
- 2026-06-19 — P1/P2 confirmed good in the running app. **Phase 3 done.** 3.1 scope
  toggle demoted to a small labeled control; 3.2 method tabs → cards with a "Default"
  badge on Search by CV + a `#methodLabel`. Wiring unchanged. Live click-through of the
  Single↔Multiple switch still worth a quick look (cards hide/show correctly).
- 2026-06-19 — **Phase 4.1 done.** `/api/saved/interview` → `/api/saved/observation`
  with a legacy alias; frontend caller + docstrings updated; byte-compiles. **4.2
  (unify the seven `/chat` endpoints) remains deferred** per plan — only worth it if more
  chat surfaces appear. All non-deferred cleanup items (P1–P4.1) are now complete.
