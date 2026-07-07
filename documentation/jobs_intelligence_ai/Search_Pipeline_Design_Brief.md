# Search + Pipeline — Design Brief

> Purpose: a self-contained visual brief for generating high-fidelity mockups of the
> reworked **Search** tab and new **Pipeline** tab. Unlike
> [Client_Feedback_Rework_Spec.md](Client_Feedback_Rework_Spec.md) (which tracks
> mockup-vs-current-app decisions), this doc describes only the **target end state** —
> screens, components, states, copy, and colors — so it can be handed to a design tool
> directly. A couple of product-behavior questions are still open (noted inline as
> "Not yet finalized") but none of them block the visual layout described here.

---

## 1. Design system

**Typography:** `'Helvetica Neue', Arial, sans-serif` throughout.

**Color tokens:**

| Token | Hex | Use |
|---|---|---|
| `--ic-blue` | `#24579B` | Primary brand blue — links, icons, resting-state outlines |
| `--ic-blue-dark` | `#1C4680` | Solid fills for active/primary elements (bold surfaces) |
| `--ic-light-blue` | `#8EB4E3` | Accent — table header bands, highlights |
| `--ic-grey` | `#7F7F7F` | Secondary/inactive text and icons |
| `--ic-bg` | `#EDF1F8` | Page/panel background |
| `--ic-border` | `#E0E4EA` | Dividers, default borders |
| `--ic-text` | `#1A2332` | Primary text |
| `--ic-text-mid` | `#5A6677` | Secondary text |
| white | `#FFFFFF` | Card/panel backgrounds |
| grade green | `#1A7A2E` | "A" grade tile (solid fill, white text) |
| grade amber | `#C67C14` | "B" grade tile (solid fill, white text) |

**Recurring component patterns (apply everywhere, not just where mentioned below):**
- **Active tab / active toggle:** solid `--ic-blue-dark` fill, white bold text, rounded
  pill or rounded-rect. Inactive tab: light grey background, `--ic-grey` text.
- **Filter pill / chip (resting state):** white background, **`--ic-blue` border**, `--ic-blue`
  text — blue outline at rest, not just when selected.
- **Primary button** (e.g. "Start job matching", "Apply filters"): solid `--ic-blue-dark`
  fill, white text, rounded corners (~8px).
- **Table header row:** `--ic-light-blue` band background, bold `--ic-blue-dark` or white
  text (high-contrast, not the muted grey-on-pale-blue used previously).
- **Grade tile (M-Score):** small solid-color square/rounded tile, white bold text —
  green for A, amber for B. **No "C" tile** — weak matches are excluded entirely, not
  shown greyed out.

---

## 2. Top navigation

Two tabs, top-right of the header bar: **Search** | **Pipeline**. Whichever is active
gets the bold `--ic-blue-dark` fill + white text; the other is a light grey pill.
Top-right of the bar: language switch (EN/DE), DB-connection status dot, user chip
(avatar + name), sign-out.

---

## 3. Search tab

Three collapsible sections, each with a chevron toggle (expand/collapse animation):

### 3.1 AI Job Search with Candidate Matching
Three buttons in a row, equal width, outlined pill style:
- **Upload CV** — opens a drag-drop file zone (`.pdf/.doc/.docx/.txt`) or paste-text
  textarea.
- **Saved candidates** — opens an autocomplete/dropdown search over previously saved
  candidates by name.
- **LinkedIn profile links** — opens a textarea to paste one or more LinkedIn profile URLs.

Below the three buttons: primary button **"Start job matching."**

### 3.2 AI Job Search with Text Input
A single large textarea with placeholder copy: *"Describe the job you're looking for,
e.g. job title, location, skills or company — or paste the text of a CV. Our AI Matching
Tool will find the most relevant job adverts for you."* Primary button below it:
**"Start job matching."**

### 3.3 Job Search with Filters
Filter pills grouped under labeled sub-headings, each pill using the resting-blue-outline
style from §1:

- **Job Status:** Online since · Status · Available from · **Scraping date**
- **Region** (4-level, cascading): Federal State → District → Town → Postcode
- **Job criteria:** Job title · Occupational group · Job description · Skills · Monthly
  salary · Source
- **Company criteria:** Company · Exclude Personnel Service Providers · NACE 1 · NACE 2 · NACE 3

*Not yet finalized: whether selecting a value in one filter visually disables/hides
incompatible options in the others (cascading behavior). Render the filters with a
disabled/greyed-out option state available, since this interaction is planned.*

Primary button below: **"Start job matching."**

### 3.4 Results — Top Job Matches
- Quick-filter chip row above the table (styling per §1).
- Table columns: **AI M-Score** (grade tile, A/B only + %, with a one-line match
  rationale under the job title) · **Job Title** · **Company** · **Location** ·
  **Salary** · **Online Since** · **Contact** (contact-card style: name, email, phone).
- Each row: a **`+`** icon next to the job title opens a details popup (description, job
  category, etc.).
- Per-row action icons: an external-link-box icon ("Open job link" tooltip) and a
  download-arrow icon ("Save job" tooltip). Clicking save reveals an inline **notes
  field + status field** on that row.

---

## 4. Pipeline tab

Four independent sub-tabs, each a fully separate screen with its own filter panel, own
"Apply filters" action, and its own remembered filter state: **Jobs** | **Contacts** |
**Companies** | **Candidates**.

Each sub-tab's filter panel is scoped to that sub-tab's *already-saved* items (it
searches/narrows what's been saved into the pipeline from the Search tab — not the wider
market catalogue), and shares the same field groups as the Search filters, plus one new
group:

- Job Status · Region (4-level) · Job criteria · Company criteria (same fields as §3.3)
- **Sales filter** (new, Pipeline-only): **Sales Status** · **Candidate/Contact** (whichever
  applies to the sub-tab) · **User** (assigned salesperson/employee)
- Primary button: **"Apply filters"**

Below the filters, a saved-items table for that sub-tab, each row editable/deletable:

| Sub-tab | Columns |
|---|---|
| **Jobs** | Job Title · Company · Location · Salary · Online Since · Contact · Candidate · User · Sales Status · Notes · Saved · *Edit/Delete* |
| **Contacts** | Contact · Company · Location · # Jobs Online · # Saved Jobs · User · Notes · Saved · *Edit/Delete* |
| **Companies** | Company · Location · # Jobs Online · # Saved Jobs · User · Notes · Saved · *Edit/Delete* |
| **Candidates** | Candidate · Location · Matches · User · Notes · Saved · *Edit/Delete* |

*Not yet finalized: whether "Sales Status" applies to all four sub-tabs or only Jobs —
render it present on all four for now.*

---

## 5. Row click-through — detail views

Clicking any row (Job / Candidate / Company / Contact) in either Search or Pipeline opens
a modal — the **same modal regardless of which tab it was opened from**. These are
specced in their own document, kept separate so the views can be iterated independently
of this tab-level layout: see
[Detail_Views_Design_Brief.md](Detail_Views_Design_Brief.md).

---

## 6. Sample content (for populating the mockup)

Use realistic-looking rows rather than lorem ipsum:

- **Jobs:** "Data Engineer (m/w/d)" — Anexia Cloud Solutions GmbH — Klagenfurt, Bezirk
  Innere Stadt, Kärnten — €56,000 — online 2026-05-29 — grade A 90%, rationale "Strong
  match: Python, ETL, SQL, automation and LLM/AI skills."
  "Datenbankentwickler für DWH (m/w/d)" — COUNT IT GmbH & Co KG — Penzendorf,
  Oberösterreich — €55,356 — online 2026-06-13 — grade B 72%, rationale "Good fit: ETL,
  SQL databases and data processing alignment."
- **Contact card:** Maria Mayer · mayer@inter.com · 0901/123123.
- **Candidate/User rows:** use a placeholder staff name + role (e.g. "Roman Labuš —
  Administrator") for the `User`/assigned-salesperson column.
