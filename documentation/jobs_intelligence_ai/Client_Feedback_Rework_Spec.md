# Client Feedback — Rework Spec

> Source: `Jobs Austria AI App.pdf` — wireframe/mockup with handwritten feedback from
> the client (Acme Recruitment), received 2026-07-06. Bilingual DE/EN,
> same content both times. This doc turns his annotations into a concrete spec, section
> by section, comparing each proposal against current app behavior before deciding what
> to build.

---

## 1. Top-level navigation

**Mockup:** `Search` / `Pipeline` tabs (top-right corner). `Pipeline` is shown greyed out —
not yet built, planned as the next tab.

**Current app:** `Search` / `Saved` tabs.

**To resolve:**
- Is `Pipeline` a rename of the existing `Saved` tab, or a new tab that sits alongside it?
- Tab colors in the mockup (active = dark blue, inactive = grey) don't match our current
  IC palette styling on those tabs — needs a look.

## 2. Search tab

### 2.1 Job Search — mode selection

**Mockup:** the Job Search screen splits into three collapsible sections instead of being
shown fully expanded at once:
- AI Job Search with Candidate Matching
- AI Job Search with Text Input
- Job Search with Filters

Each has a chevron toggle in the corner and an expand/collapse animation, so only the
section currently in use takes up vertical space.

**Current app:** No collapsible sections anywhere on the Search tab — candidate input and
the filter bar (`index.html:74-236`) are both always fully visible. There's also no hard
split between "modes" today: the filter bar sits *below* the candidate-matching input and
narrows/refines the AI match results, it isn't a separate, standalone search mode you pick
instead of matching.

**To resolve:**
- Are the mockup's three sections meant to be mutually exclusive modes (pick one, the
  others stay collapsed/unused), or just three collapsible groups that can all be open
  together — functioning the way matching + filters already work today (filters refine
  matching results)?
- If mutually exclusive: does "Job Search with Filters" become a pure browse-without-AI
  mode (no M-Score, just filtered listings)? That's a bigger behavioral change than
  collapsing some UI, and changes what "Results" means depending on which mode is active.

### 2.2 AI Job Search with Candidate Matching — inputs

**Mockup:** three buttons in a row: `Upload CV`, `Saved candidates`, `LinkedIn profile links`.

**Current app:** two mode-tabs — `Search by CV` (drag-drop upload or paste text,
`index.html:142-151`) and `From LinkedIn` (paste one or more profile URLs,
`index.html:154-162`). The LinkedIn path is fully wired, not a stub — it scrapes via the
Apify `harvestapi` actor (`/api/candidate/enrich-linkedin`,
`blueprints/candidate.py:63`) as the first step of "Run matching," and every imported
profile is also saved to `Saved → Local`.
`Saved candidates` isn't a third input mode today — it's a separate autocomplete lookup
(`#dbCandDropdown`, `index.html:74-84`) for finding an existing saved candidate by name,
not presented alongside CV/LinkedIn as an equal option.

**To resolve:**
- Promote `Saved candidates` to a full third button/tab next to CV and LinkedIn, matching
  the mockup's three-way layout?

### 2.3 AI Job Search with Text Input

**Mockup:** its own collapsible section, a single textarea: "Describe the job you're
looking for, e.g. job title, region, skills or company — or paste the text of a CV. The AI
Matching Tool finds the most relevant job ads."

**Current app:** no standalone "text input" search. The CV zone's textarea doubles as a
free-text field, but it's nested under Candidate Matching and feeds the same
candidate-matching pipeline (find jobs that match a candidate/CV) — there's no separate,
job-description-based search today.

**To resolve:**
- Is this meant to be a genuinely different search — describe the *job* you want
  (title/region/skills/company) as prose, i.e. a natural-language version of the filter
  fields — as opposed to candidate matching, which describes a *candidate* (CV) to match
  against jobs? The mockup's own copy blurs this ("...or paste the text of a CV"), so it
  may end up overlapping with the existing CV-paste flow. Worth deciding up front whether
  this is one merged input or two distinct pipelines before building it.

### 2.4 Job Search with Filters

**Mockup fields:**
- Job Status: Online since / Status / Available from
- Scraping Date (new)
- Region: Bundesland / Bezirk / Ort / PLZ (4-level hierarchy)
- Job Kriterien: Job title / Occupational group / Job description / Skills / Monthly
  salary / Source
- Kriterien Unternehmen: Company / Exclude Personnel Service Providers / NACE 1 / NACE 2 /
  NACE 3
- Cascading behavior (explicit instruction): "Only display relevant filter values. Once a
  value is selected in one filter, all incompatible values in the remaining filters should
  be disabled or hidden. Users should only be able to select valid filter combinations."

**Current app:** a flat filter bar (`index.html:214-236`), all options populated once from
`GET /api/filters` on page load (`search.js:33-63`), no cascading — every field is an
independent, statically-populated select or plain input:
- State (dropdown) — covers `Bundesland` only, no Bezirk/Ort/PLZ breakdown
- City (free text) — closest match to `Ort`, not linked to State
- Keywords/title (free text) — matches `Job title`
- Occupational group (dropdown, Austria-only) — matches `Berufsgruppe`
- Portal/Source (dropdown) — matches `Quelle`
- Work time / Employment relationship / Education (dropdowns) — not present in the mockup
  at all
- Two checkboxes: "Freeze all results", "Show weak (C) matches"

Missing vs. the mockup: Online since / Status / Available from, Scraping Date, the
Bezirk/PLZ region levels, Job description text filter, Skills filter, Monthly salary
filter, Company name filter, Exclude Personnel Service Providers, NACE 1–3.
Present today but absent from the mockup: Work time, Employment relationship, Education.

**To resolve:**
- Keep Work time / Employment relationship / Education alongside the new fields, or is the
  mockup implicitly proposing to replace the filter set wholesale?
- Region hierarchy: do we have Bezirk/PLZ data to actually cascade
  Bundesland → Bezirk → Ort → PLZ, or is that new data plumbing?
- NACE 1/2/3 and "Exclude Personnel Service Providers" — do we have NACE codes on
  companies in the current DB, or is this new data we'd need to source?
- Cascading filters is a real architecture change (static "load once" dropdowns →
  dynamic, dependency-aware option loading), not a styling tweak — confirm it's in scope
  for this pass rather than a follow-up, since it touches State→City and the NACE/region
  hierarchies specifically.

### 2.5 Results — matching table

**Mockup:**
- Two chips above the table: `Top 20 matches` and `Weak matches` (shown checked, labeled
  "Quick Filter").
- `AI M-Score` column: a letter grade + percentage (e.g. "A 90%", "B 72%") with a one-line
  match rationale under the job title.
- `+` icon next to the job title opens job details (description, job category, etc.) in a
  popup instead of a direct link-through.
- Clicking "Save" reveals an inline notes field + status field.
- Two per-row icons — an external-link-box icon (open job link) and a download-arrow icon
  (save job) — each with a hover tooltip.

**Current app** (`search.js`): weak (C-grade) matches are **already** hidden by default
(`_showWeakC`, `search.js:156-163, 572-574`) and only reappear via the "Show weak (C)
matches" checkbox; the results status line already reports counts per grade — `N strong
(A) · N good (B)` and, only if the toggle is on, `· N weak (C)` (`search.js:658-660`).
There's no "Top 20 Matches" cap today — the table just shows whatever non-C results the
matching pipeline returned. Save/open-link icons use different glyphs than the mockup, but
work the same way.

**Decisions:**
- Drop weak (C) matches from the results entirely — no need to keep them reachable via a
  toggle at all. (Whether the "Top 20 Matches" label/tab sticks around is still an open,
  softer question — not settled either way.)
- To keep a full scope of good (A/B) results once C's are excluded, **run the matching
  pipeline twice by default** (deeper retrieval — most likely doubling `MATCH_CYCLES`,
  the parallel-vector-retrieval count `run_matching` already uses, or running the full
  cycle set twice and merging). This is a **backend change**, not a UI toggle.
- Save-job / open-link icons: purely a glyph swap to match the mockup's icon set, no
  behavior change.

**Not yet covered (from the mockup, still to address):**
- The `+` icon opening job details in a popup.
- The inline notes + status field appearing when "Save" is clicked.

## 3. Pipeline tab

**Mockup:** the new `Pipeline` tab (Sales Pipeline "Kundenunternehmen" / "Client
Companies") has 4 sub-tabs: `Jobs`, `Kontakte`, `Unternehmen`, `Kandidaten`. Each sub-tab
gets **its own connected filter set** scoped to that entity — not one shared global filter
bar reused across all four.

### 3.1 Sub-tab structure and filters

**Mockup, per sub-tab** (Jobs / Kontakte / Unternehmen / Kandidaten — fields repeat across
all four with the entity swapped in):
- Deal-Filter (entity-specific heading: "Deal-Filter Jobanzeigen" / "…für Kontakte" / etc.)
- Job Status: Online seit / Status / Verfügbar ab
- Region: Bundesland / Bezirk / Ort / PLZ
- Job Kriterien: Job Titel / Berufsgruppe / Job Beschreibung / Fähigkeiten / Monatsgehalt / Quelle
- Kriterien Unternehmen: Unternehmen / Mit Personaldienstleister / NACE 1–3
- **Sales Filter** (new layer, not part of Search): Sales Status + Kandidat/Kontakt + User
- `Filter ausführen` button, then a saved-items table with edit/delete

**Current app:** the "Saved" tab is **one shared panel**, not four independent sub-tabs —
a collection toggle (`Candidates | Jobs | Companies | Contacts`,
`index.html:269-274`) swaps the data source under an otherwise identical grid
(`setSavedCollection`, `saved.js:175-191`). There are **no filters at all** on this tab
today — no Job Status, Region, Job/Company criteria, and no Sales Filter. (The
work_time/employment_relationship/education filters added recently landed in the
**Search** tab's filter bar, not here.)

The closest thing to a mockup Deal-Filter that exists today is **"Browse market" mode**
(Companies/Contacts only, `#svModeToggle`, added in `dbd2743`): a toggle that swaps "my
saved" rows for a live, search-driven read of the *entire* market catalogue
(`GET /api/market/companies|contacts?q=`). It's a single search box, not a faceted filter
bar — no region/criteria/status filtering on the market catalogue.

**Saved-items table today, per collection** (`saved.js:77-141`):
- **Jobs**: Title, Company, Location, Candidate, Status (5-stage sales pipeline:
  new/in_progress/proposal_sent/won/lost — `saved.py:56`), Notes.
- **Companies**: Company, Industry, Location, Notes, Saved date.
- **Contacts**: Name, Title, Company, Open jobs (active market jobs the contact is
  linked to, annotated server-side; also filterable via the Deal-Filter's
  "Open jobs (min.)" field — contacts-only), Email, Notes, Saved date.
- **Candidates**: Name, Title, Seniority, Location, Status (hiring pipeline —
  New/Contacted/Interviewing/Placed/Rejected, separate concept from Jobs' sales status),
  Matches, Saved by, Last saved. No Notes field here today.

So: a Sales Status concept **only exists on Jobs** today; there's **no assigned-User /
salesperson field anywhere** (only "Saved by," i.e. who created the row — not something
reassignable); Companies/Contacts have no status field of any kind; and several mockup
columns are simply missing (Online seit / Gehalt / Kontakt on Jobs; job-online-count on
Companies; saved-job-count on Companies and Contacts). Contacts' job-online-count landed
as the "Open jobs" column + Deal-Filter min-jobs field (2026-07-06).

**Note on the mockup's saved-items table screenshots:** the sample rows under all four
sub-tabs are the same leftover data ("Roman Labuš / Python Developer…") from a real
screenshot of the current app, pasted under the new column headers — the row values don't
actually line up with his proposed columns. Treat only the **column headers** as intent,
not the sample row content.

**Decisions:**
- Structural: rebuild `Saved`/`Pipeline` into **4 independently-filtered sub-tabs**
  (Jobs / Kontakte / Unternehmen / Kandidaten), matching the mockup — each gets its own
  filter panel, its own "run filter" action, and its own remembered filter state, rather
  than today's single shared grid behind a collection toggle. This is a real rebuild of
  the tab, not a bolt-on to the existing toggle.
- **Narrow reading of Deal-Filter:** it only searches/narrows what's already been saved
  into the pipeline — people, deals, and companies get **siphoned into Pipeline from the
  Search tab** (via Save), and Deal-Filter is a filter *over that saved set*, not a
  browse-the-whole-market search. "Browse market" stays a separate, distinct feature (its
  job is finding new things to save in the first place); it does not merge into
  Deal-Filter.

- **"See other employees' deals for a company" — use the existing access model, no new
  field.** [FRONTEND_DB_REWORK_PLAN.md](planning/FRONTEND_DB_REWORK_PLAN.md) already specs
  `app_user.visibility: own | all`, scoped within the firm's `account_company` — `all`
  (default) shows every colleague's saved items, not just your own. Combined with the
  `Unternehmen` filter and the per-row `User` column, that already answers "who else is
  working this company" without a new mechanism. A more granular, per-company override
  (seeing colleagues' deals for one company while otherwise staying in `own` mode) was
  considered and **rejected** — it re-opens a `selected`-visibility-level idea the boss
  already deliberately dropped on 2026-06-29; not worth the complexity.

**To resolve:**
- Sales Filter's `User` field doesn't exist on any table today (`saved_jobs` /
  `saved_companies` / `saved_contacts` / `saved_candidate` — need an assignable
  owner/salesperson column, distinct from "Saved by"). Maps onto the rework plan's
  `owner_id` — likely the same column, not a separate one.
- Does Sales Status expand to Companies/Contacts/Candidates (new columns/values needed),
  or does the mockup only really mean it for Jobs, with the other three tabs just
  reflecting counts/rollups of their linked jobs?

### 3.2 Row click-through — detail views

**Mockup:** no explicit annotation for what a Pipeline row click shows — the client's only
detail-view instruction was the Search results' `+` icon opening a job popup (§2.5); the
Pipeline sub-tab screenshots only annotate `bearbeiten`/`löschen` (edit/delete) on rows.

**Current app:** already has full, reusable detail views for all four entities —

- **Job:** a complete modal (`modal.js:102 openJobModal`) — grade/score header, meta grid
  (location, salary, portal, category, employment, education, dates), skills chips,
  description with Translate/Compact toggles, a match-reason line, lazy-loaded salary
  chart / quality / candidate-strength panels, a per-job AI chat sub-thread, and the
  save/status footer. Identical whether opened from Search results or a Saved Jobs row.
- **Candidate:** a complete modal (`candidate.js:945 openCandidateDetail`) — status badge,
  saved-by owner, match count, contact line, fact chips (industry, role, languages,
  salary expectation, availability), AI summary, skills, experience, education,
  certifications, and a **Matched jobs** list (grade, title, company, salary, pipeline
  status).
- **Company:** a complete panel (`candidate.js:621 openCompanyPanel`, backed by
  `GET /api/company`) — job count, avg salary, state count, AI-generated hiring-profile
  summary, top roles/sectors, salary range, active locations, recent postings, and a
  **Contacts list** (each with its own Save button).
- **Contact:** a dedicated modal (`saved.js:402 openContactDetail`) — title/company,
  email/phone/LinkedIn, location, saved date, notes, plus an async **Jobs** section
  (`GET /api/contact/jobs`) listing that contact's associated postings.

One gap: Company and Contact detail views only exist for **"My saved"** rows today —
"Browse market" rows (the wider-catalogue search) show name + a `+ Save` button only, no
click-through. This doesn't block Pipeline, since §3.1 already decided Pipeline only ever
shows already-saved rows (Browse market stays Search-side).

**Decision:** Pipeline's four sub-tabs reuse these exact same modals/panels verbatim for
row click-through — no new detail-view design needed. Clicking a Job/Candidate/Company/
Contact row in Pipeline opens the identical modal already built for Search/Saved, keeping
one detail view per entity instead of building parallel ones.

## 4. Visual design & colors

**Current brand tokens** (already defined, `app.css:4-14` — no new palette needed, this is
about which existing tokens apply where):
- `--ic-blue` `#24579B` — primary brand color
- `--ic-blue-dark` `#1C4680` — deeper shade, used for brand surfaces/hovers
- `--ic-light-blue` `#8EB4E3` — accent
- `--ic-grey` `#7F7F7F`
- `--ic-bg` `#EDF1F8` — soft blue-tinted panel background
- `--ic-border` `#E0E4EA`
- `--ic-text` `#1A2332` / `--ic-text-mid` `#5A6677`
- Font is still `'Segoe UI', Arial, sans-serif` (`app.css:17`) — Helvetica Neue was the
  planned rebrand font per an earlier decision but was **never actually applied**.
  **Decision: switch to Helvetica Neue now** (`'Helvetica Neue', Arial, sans-serif`).

**Mockup's color language:** solid dark-blue fills with white text for primary
actions/active tabs, blue-outlined white pills for filter fields (blue border shown
regardless of state), a light-blue banded table header, green/yellow/grey grade
indicators. This is already consistent with the token palette above — the question isn't
new colors, it's which existing UI elements should switch from the *subtle/pastel* variant
already in use to the *bold/solid* variant, to match what's drawn.

**Decisions — adopt all four:**
1. **Top-level tabs** (Search/Pipeline, and Pipeline's Jobs/Kontakte/Unternehmen/Kandidaten
   sub-tabs): today's active tab (`.tab-btn.active`, `app.css:34`) is a pale blue tint
   (`#eef2fa` bg + dark-blue text) — subtle. The mockup's active tab is a bold solid
   dark-blue fill + white text. **Adopted:** reuse the bold style our own CSS already has
   elsewhere for exactly this pattern — `.mode-toggle-btn.active` (`app.css:28`, solid
   `--ic-blue-dark` + white) — rather than inventing something new.
2. **Filter fields:** today's `.chip` (`app.css:84-86`) is grey-bordered/grey-text by
   default, turning blue only once selected (`.chip.on`). The mockup shows every filter
   field permanently blue-outlined, selected or not. **Adopted:** blue outline as the
   resting state for filter pills, not just the active state.
3. **Results/saved-items table header:** today's `thead th` (`app.css:577`) is a pale
   `--ic-bg` background with small grey uppercase text — quite muted. The mockup shows a
   more saturated light-blue band with bolder text. **Adopted:** raise the contrast to
   match (e.g. `--ic-light-blue`-tinted band, darker header text).
4. **Grade badges (A/B/C):** today's are soft pastel pills (`grade-a` light green /
   `grade-b` light yellow / `grade-c` pale grey, `app.css:584-587`) vs. the mockup's
   bolder solid-color square tiles. Same color choices already, just different
   intensity/shape. **Adopted**, lowest priority of the four — cosmetic only.

## 5. Implementation status (2026-07-06)

All three approved mockups (`Search Tab Redesign`, `Pipeline Tab Redesign`,
`Detail Views Redesign`) have been implemented and verified in-browser + via the full
test suite (147 passed). Every remaining "To resolve" / "Not yet covered" item above is
now resolved as follows — a few landed slightly differently than first sketched, noted
explicitly rather than silently:

- **§1 Navigation:** `Pipeline` replaces `Saved` in the same nav slot (confirmed via the
  mockups showing only 2 top-level tabs). Bold active-tab styling adopted.
- **§2.1 Mode selection:** built as a numbered 1/2/3 collapsible stepper
  (`.stepper`/`.step-card`, `index.html`), each independently expandable — not mutually
  exclusive. Each step keeps its own "Start job matching" entry point, but all three feed
  the *same* underlying matching pipeline (consistent with today's filters+matching
  behavior) rather than three separate pipelines.
- **§2.2 Candidate matching inputs:** `Saved candidates` promoted to a full third tile
  (`#zone-saved`), with a persistent search/list panel replacing the old small dropdown.
- **§2.3 Text Input:** resolved as *one merged pipeline* — Step 2's textarea activates CV
  mode and feeds the exact same candidate-matching path as the CV-paste box (no second
  pipeline built).
- **§2.4 Filters:** rebuilt as grouped field-cards. NACE 1/2/3 turned out buildable for
  **both** countries (confirmed live: `companies_creditreform.industry_code` for AT,
  `companies_finstat.sk_nace` for SK) — implemented with real cascading dropdowns.
  "Exclude Personnel Service Providers" is Slovakia-only
  (`companies_finstat.personal_service_provider` — no AT equivalent exists). District/
  Bezirk was omitted entirely — confirmed via live DB check that no district-level data
  exists in either country's `locations` table; would need a new static PLZ→Bezirk
  reference table (follow-up, out of scope here). Work time/Employment/Education kept
  alongside the new fields.
- **§2.5 Results:** weak (C) matches now excluded from rendering entirely (no toggle);
  retrieval breadth doubled (`MAX_NUM_RESULTS` 30→60,
  `services/search/config.py`) to keep a full scope of A/B results. The `+` icon reuses
  the existing full job-detail modal rather than a separate lightweight popup (avoided
  building a second, thinner detail view alongside the one in §3.2). Inline Notes+Status
  row on Save implemented and verified (PATCHes `/api/saved/<job_id>` on blur/change).
- **§3 Pipeline structure:** implemented as 4 sub-tabs, each with its own Deal-Filter +
  Sales Filter panel and **independently remembered filter state**
  (`saved.js:_pipelineFilters`) — verified switching tabs does not reset another tab's
  filters. Under the hood this reuses the existing shared-grid-plus-toggle architecture
  (one table component, data source swapped per tab) rather than four fully separate DOM
  sections — satisfies the functional requirement (independent filters, independent
  state) without the larger rebuild cost of true duplication.
- **Sales Filter `User` field:** resolved cheaply — `owner_id` already existed as an FK on
  all four `saved_*` tables (from the DB rework), so no schema change was needed. Added
  `GET /api/saved/users` (company-scoped colleague list) and a `user_id` query param on
  the four list endpoints. The mockup's 3rd Sales Filter field (Candidate/Contact
  cross-link) was simplified out — only Sales Status + User shipped.
- **Sales Status scope:** implemented exactly as recommended — native filter on
  `saved_jobs.status` for Jobs, an `EXISTS`-subquery rollup for Candidates (via
  `saved_candidate_id`), and **skipped for Companies/Contacts** (no clean link from
  `saved_jobs` to those tables without a fragile string-match) — their Sales Status field
  is shown disabled/locked in the UI rather than silently doing nothing.
- **§3.2 Detail views:** reused verbatim as planned; additionally restyled in Phase 2
  (dark-blue header on the Job modal to match the other three, field-card meta grid,
  semi-transparent status/match-count pill badges moved into the Candidate modal's header).
- **§4 Visual design:** all four adopted decisions (Helvetica Neue, bold tabs, resting-blue
  filter fields, higher-contrast table headers) implemented and confirmed via computed
  styles in-browser.
