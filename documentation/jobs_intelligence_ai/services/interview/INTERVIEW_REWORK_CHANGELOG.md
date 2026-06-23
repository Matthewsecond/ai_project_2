# Interview Scorecard Rework + UX Cleanup — Session Changelog

> **Note (rework 2.3 #3):** the backend has since moved from the single
> `services/interview_helper.py` to the `services/interview/` package
> (`orchestrator.py` + `config.py`) and its model calls now use Structured Outputs — see
> [README.md](README.md). Paths below reflect the layout at the time of this changelog.

_2026-06-19. Summary of the work done in this session. Files are under
`src/jobs_intelligence_ai/`. Frontend = `web/templates/index.html` (inline JS/HTML).
Verified throughout with `node --check` (inline JS) + Python parse/route checks + direct
model calls. **Standing gap: no live in-browser click-through** (needs the running app +
a logged-in session); everything else is statically/▸model-verified._

---

## 0. Model upgrade
- `CHAT_MODEL` default `gpt-5.4` → **`gpt-5.5`** in `config/settings.py` (verified the API
  accepts it). Classifier left on `gpt-5.4-nano` (no 5.5-nano exists). Doc/comment
  references to `gpt-5.4` updated.

---

## 1. The interview rework (the main work)

The job-detail modal's interview scorecard went from a one-shot "answer → score" panel to
a conversation-aware interview helper. Backend lives in
`services/interview_helper.py` + `web/blueprints/interview.py`; UI in `index.html`.

### 1a. Import prepared questions/answers
- **`POST /api/interview/extract`** — upload `.docx` / `.pdf` / `.txt`, returns plain text.
  `.docx` via zip+`document.xml` (no new dependency); `.pdf` reuses `pypdf`.
- **`POST /api/interview/parse`** (`InterviewHelper.parse_questions`) — model splits a
  free-form interview doc into ordered `{question, answer}` pairs (no markers needed; not
  every question has an answer). Proven on the user's real `questions.docx` (6 Q, 4 A).
- UI: **📥 Import** panel (paste or file) → parsed rows become editable, removable
  questions with answers prefilled; **⚡ Analyze all**; every question deletable so an
  imported set can replace the AI one.

### 1b. Richer shared context (no RAG — just prompt assembly)
- `_context()` now includes **SALARY** + **LOCATION** (propagates to every interview call).
- New **`_others_block()`** = compact "INTERVIEW SO FAR" digest of other answered
  questions (trimmed/capped). Fed into `analyze_answer` and `suggest_followup` via an
  `others` param → cross-answer awareness (decision: feeds per-answer scoring too).
- **`POST /api/interview/context`** (`preview_context`) + a **🔍 AI context** panel that
  shows the exact assembled briefing note (so what the user sees = what the model gets).

### 1c. Seniority/level calibration
- Shared `_CALIBRATION` block appended to all interview prompts: judge against the level
  the posting asks for (junior vs senior, must-have vs nice-to-have), so scoring and the
  follow-up "stop" decision are level-aware.

### 1d. Follow-up suggestions ("expand the conversation")
- **`POST /api/interview/followup`** (`suggest_followup`) — on-demand **💡 Suggest
  follow-up** per answered question. Sends the whole thread; model proposes ONE probe or
  returns `exhausted:true` (it **stops itself** — no endless questions). `_coerce_followup`
  forces exhausted on an empty question.
- UI: suggestion chip → **➕ Add** inserts the follow-up **nested under its parent**
  (`followupTo`, `↳` badge); **✓ Enough context** marker when exhausted; cascade-delete of
  follow-up subtrees. Persists in `extras.interview`, restores on reopen.

### 1e. Conversational completeness loop (the key behavioural change)
- `analyze_answer` now **first judges complete vs in-progress**. A clarifying/scoping
  question is treated as a legitimate, often positive move — **not** an auto-fail (fixed
  the "12% for asking a smart question" problem; it now holds as "in progress" and scores
  ~78 once answered).
- Returns `complete / status(answer|clarifying|partial) / needs / score(null when open)`.
  `final=true` = the **⏎ Score now** override.
- UI: in-progress pill + guidance (no score); **only complete answers** feed the summary,
  assessment deltas, and cross-answer context; auto-summary waits for all-complete.

### 1f. Live candidate assessment + movement deltas
- The aspect assessment (`assess_candidate`) refreshes after each complete answer.
- Added **▲/▼ movement badges vs a baseline** (first assessment, captured once and
  persisted); per-answer step shown on hover. So you can see which categories the
  interview improved or worsened.

### 1g. Modal lock ("freeze the window")
- **🔓/🔒** toggle in the job-modal header: when locked, an accidental outside click or
  Esc won't close it (× still does); choice remembered in `localStorage`. Fixes
  accidental loss of an in-progress interview.

### Interview endpoints (final set)
`/api/interview/`: `questions · extract · parse · analyze · context · followup ·
summarize · assess`.

---

## 2. Whole-app workflow review

Two read-only explorers mapped the frontend journey + backend. Verdict: **sound engine
and good ideas; the clunk is information architecture + state-awareness, not the engine.**
It reads as "a pile of powerful panels" rather than one guided funnel; the friction is in
the **seams** (state lost between stages) and **buried depth**. Full plan +
prioritization in `CLEANUP_PLAN.md`.

---

## 3. UX cleanup (implemented)

### Phase 1 — silent state-decay seams (all in `index.html`)
- **Stale-score warning** — `#staleScoreNotice` + `_updateStaleNotice()`: when results are
  frozen and `buildCandidateText()` ≠ `_scoredAgainstText`, show a banner with a one-click
  **Re-score**.
- **Reset identity on input-mode switch** — `_resetCandidateOnModeSwitch()` drops the
  derived candidate (name/profile/dup-warning) when the `.mode-tab` changes, **preserving**
  each zone's typed text.
- **Cluster "← Back to segments"** — `_mcDrilledFrom` flag + `#backToSegments` link returns
  from a drilled candidate to the segment view.

### Phase 2 — modal clarity
- Active-state on description buttons: **already present** (no change).
- **Relabeled "CV Questions" → "Interview"** to surface the scorecard.

### Held / not done
- **Phase 3** (primary input path: separate single/multi toggle from input tabs, mark a
  default) — deliberately held until P1/P2 are click-tested.
- **Phase 4** (backend hygiene: rename `/api/saved/interview` collision; unify the 7
  `/chat` endpoints) — opportunistic; 4.2 deferred.

---

## 4. Verification status
- Inline JS: `node --check` clean after every change.
- Backend: Python parse + Flask `url_map` route checks; `_coerce_*` unit-style checks;
  live model calls confirmed the follow-up stop and the completeness gate on real text.
- **Not done anywhere: the live browser click-through** (running app + logged-in session).
