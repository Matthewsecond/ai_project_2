# Frontend Design

## Structure

The frontend is an `index.html` shell (pure markup, served by Flask) plus **ES modules** under
`static/js/`. No build step — the browser loads the modules directly. Styling is plain CSS in
`static/css/` (`app.css` is the main sheet, in the IC brand palette; `feedback.css`,
`saved-dashboard.css` are add-ons).

`static/js/boot.js` is the entry point (`<script type="module">`). It imports every feature
module — most register their handlers and `app` methods as a **load-time side effect** — and owns
tab routing, the global delegated-action dispatcher, the feedback widget, and init
(`DOMContentLoaded → app.loadFilters()`).

### Modules

| Module | Responsibility |
|--------|----------------|
| `boot.js` | Entry: imports modules, tab routing, action dispatch, feedback widget, init |
| `state.js` | The shared `app` object and the `_ACTIONS` handler registry |
| `api.js` | `fetch` wrapper (`api.get` / `api.post`, JSON + error handling) |
| `search.js` | Search tab: run matching, results table, streaming meter, filters |
| `candidate.js` | Candidate input zones, profile card, **company panel** (`openCompanyPanel`), save company/contact |
| `candidate-examples.js` | Bundled demo candidates + the "Example candidates" dropdown |
| `assistant.js` | Candidate-assistant chat — discuss, edit the CV, or widen/re-aim the search (one-click re-search) |
| `saved.js` | Saved tab — the four collections |
| `modal.js` | Job-detail modal |
| `interview.js` | Interview tools |
| `export.js` | Result export — CSV + Excel (matching results), XLSX pipeline, PDF report |
| `util.js` | Helpers (`esc`, formatting, …) |

---

## Action dispatch (no inline `onclick`)

Markup never references global function names. Instead elements carry `data-action="name"` (plus
`data-*` params), and `boot.js` runs a single delegated listener per event type that looks the name
up in the `_ACTIONS` registry:

```javascript
document.addEventListener('click', function(e) {
  const el = e.target.closest('[data-action]');
  if (!el) return;
  const handler = _ACTIONS[el.dataset.action];
  if (handler) handler(el, e);
});
```

Parallel registries exist for `data-input-action` (input), `data-change-action` (change),
`data-keydown-action` (keydown), and `data-blur-action` (focusout). Each feature module registers
its handlers into `_ACTIONS` next to its own code. This decoupling is what allowed the old single
inline `<script>` to be split into ES modules.

Company names are a small special case: any `.company-link[data-company]` (e.g. in a results row)
is handled by a dedicated delegated click in `boot.js` that calls `app.openCompanyPanel(name)`.

---

## Tabs

```
[ Search ] [ Saved ]
```

Two top tabs (`.tab-btn[data-tab]` → `.tab-panel#tab-<id>`). `_activateTab('saved')` also calls
`app.openSavedTab()`. The old Chat / Map / Analytics / Radar tabs were removed in the two-tab
collapse; the guided-builder and multi-CV-clustering code was removed from `master`
entirely on 2026-07-02 (it lives on `develop`).

---

## Search tab

**Candidate input** — the recruiter describes the candidate via one of the input zones (CV upload
/ paste, free-text description, or LinkedIn import). A checkbox by
"Run matching" auto-saves the candidate on each run.

**Filter bar** — `State · City · Keywords · (Category, Austria only) · Portal`, populated on load
via `/api/filters`, sent with `/api/match`.

**Results table** — Score · Job title · Company · Location · Salary · Portal · Posted · Actions.
- The job title opens the **job-detail modal** (`modal.js`).
- The company cell is a `.company-link` → opens the **company panel**, and shows a contact
  indicator (batch-loaded via `POST /api/jobs/contacts`) that opens a per-job contacts panel
  (`#jcModal`).

---

## Company panel (`#coModal`, `candidate.js`)

Opened by `openCompanyPanel(name)`. Layout:

```
┌─ 🏢  Swiss Re                         [＋ Save company] [×] ─┐   ← header (persistent)
│      100 active jobs · Bratislavský kraj                     │
├──────────────────────────────────────────────────────────────┤
│  100 Active jobs   €2,366 Avg salary   1 State                │
│  Hiring profile:  <AI summary>                                │
│  Top roles · Sectors · Salary range · Active in · Posted on   │
│  Recent postings: …                                           │
│  Contacts (13):  <name>  [Save]  …                            │
└──────────────────────────────────────────────────────────────┘
```

The **Save company** button lives in the modal **header** so it's available the instant the panel
opens — it doesn't wait for the full profile. On open, `_prepCompanySaveBtn(name)` reveals it and
kicks off `GET /api/company/id?name=` (fast: id only, no LLM) to enable it, while the heavy
`GET /api/company` (which includes the AI hiring-profile summary — the slow part) fills in the body
in the background. Save posts `{ target_company_id, snapshot }` to `POST /api/saved/companies`;
`added:false` shows "✓ Already saved". Each contact row has its own Save button
(`save-contact` → `POST /api/saved/contacts`).

---

## Job-detail modal (`modal.js`)

Opened from a result's job title. Sections: header (grade · score · title · company), a
location/salary/portal/category/posted/id grid, skills, description (with translate/compact),
a salary-analysis chart for the occupational group (see [SALARY_ANALYSIS.md](../services/stats/SALARY_ANALYSIS.md)),
and actions (save to a candidate, open posting). Per-job AI helpers call the `job_detail`
blueprint (`/api/job_chat`, `/api/desc_*`, `/api/candidate_strength`).

---

## Saved tab (`saved.js`)

The shared, company-scoped database view — a collection switcher over four `saved_*` tables:

```
[ Candidates ] [ Jobs ] [ Companies ] [ Contacts ]
```

Each button is `data-action="set-saved-collection" data-collection="…"`. Rows are scoped to the
caller's `account_company` with `own`/`all` visibility, read from `/api/saved`,
`/api/saved/candidates`, `/api/saved/companies`, `/api/saved/contacts`. This is the collaboration
surface — everyone in the company works off the same saved data. The Candidates collection includes
a **Saved by** column (which user saved the row).

The Jobs collection's **Status** cell is an always-live dropdown (no row-Edit needed) over the
sales pipeline `new → in_progress → proposal_sent → won | lost` — changing it PATCHes
`/api/saved/<job_id>` immediately and tints the select per stage. Canonical codes are stored in
`saved_jobs.status`; the UI maps them to labels (i18n-ready). The job-detail modal's footer select
(`#modalStatusSel`) sets the initial status with the same codes, and the saved blueprint rejects
anything outside the five codes (400).

### Candidate detail modal (`#candModal`, `candidate.js`)

Clicking a candidate name (`.cand-name-link`) opens `openCandidateDetail(name, row)` — a large modal
(same styling as the company panel). The grid row fills the header instantly; `GET
/api/saved/load?name=` fetches the full parsed profile (contacts, skills, experience, education,
certifications, summary) plus the candidate's **saved matched jobs**. An inline **Edit** toggle turns
the key fields (title, seniority, status, location, contacts, languages, salary, availability, skills,
summary) into a form and `PATCH`es `/api/saved/candidate/<name>` on save, then refreshes the grid.

### Detail views for Jobs / Companies / Contacts

The first column of each of the other three collections is also a `.cand-name-link`
(`data-action="open-saved-detail"`); clicking it opens a detail view for that row via
`openSavedDetail(key)` in `saved.js`, which dispatches by collection:

- **Jobs** → reuse the search tab's **job-detail modal** (`app.openJobModal`, `modal.js`). The saved
  row already carries the full `job_snapshot`, so it's stored via `storeJob` and handed to the modal.
- **Companies** → reuse the **company panel** (`app.openCompanyPanel(name)`, `candidate.js`), which
  loads the live market profile (jobs, salary stats, contacts) from `/api/company?name=`.
- **Contacts** → a small dedicated modal (`#ctModal`, `openContactDetail`) summarising the saved
  snapshot (title, company, email/phone/LinkedIn, notes), plus a **Jobs** section listing the active
  jobs the contact is linked to — loaded from `/api/contact/jobs?contact_id=` (View_Jobs_Contacts).

---

## Shared state (`state.js`)

State and cross-module wiring hang off the `app` object (assigned to by each module) rather than
loose globals. `_ACTIONS` is the delegated-handler registry described above. `boot.js` also stores
the current candidate name and exposes `getCandidateName` / `_activateTab` / `_feedbackContext` on
`app` so other modules can call them without a circular import.
