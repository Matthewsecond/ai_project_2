# Detail Views — Design Brief

> Purpose: a self-contained visual brief for the four entity detail views — **Job**,
> **Candidate**, **Company**, **Contact** — used identically from both the Search tab and
> the Pipeline tab (see [Search_Pipeline_Design_Brief.md](Search_Pipeline_Design_Brief.md)
> for the surrounding screens). Handed to a design tool on its own so these views can be
> iterated independently of the tab-level layout.

---

## 1. Design system (shared with Search + Pipeline)

**Typography:** `'Helvetica Neue', Arial, sans-serif`.

| Token | Hex | Use |
|---|---|---|
| `--ic-blue` | `#24579B` | Links, icons, resting-state outlines |
| `--ic-blue-dark` | `#1C4680` | Solid fills — buttons, avatars, primary surfaces |
| `--ic-light-blue` | `#8EB4E3` | Accent bands / highlights |
| `--ic-grey` | `#7F7F7F` | Secondary text/icons |
| `--ic-bg` | `#EDF1F8` | Panel background |
| `--ic-border` | `#E0E4EA` | Dividers |
| `--ic-text` | `#1A2332` | Primary text |
| `--ic-text-mid` | `#5A6677` | Secondary text |
| grade green | `#1A7A2E` | "A" grade tile |
| grade amber | `#C67C14` | "B" grade tile |

## 2. Shared modal conventions

All four views share one modal shell:
- Centered overlay, white card, rounded corners (~12px), soft drop shadow, dimmed
  backdrop.
- Max width ~640–720px, scrollable body if content overflows, header stays visible.
- Close (`×`) button top-right.
- Header row: an identity block (name/title + a couple of key facts) followed by a
  primary action (Save, or Edit for already-saved entities).
- Body organized as stacked sections, each with a small caps or bold label, separated by
  thin `--ic-border` dividers.
- Recurring sub-components, styled consistently across all four views:
  - **Chips** (skills, facts, certifications): rounded-pill, `--ic-bg` or light-blue-tint
    background, `--ic-blue` text.
  - **Grade tile** (A/B, used in Job and inside Candidate's matched-jobs list): small
    solid-color square, white bold text — green for A, amber for B.
  - **List rows** (experience, education, matched jobs, contacts, associated postings):
    a compact two-line row — bold primary line, grey secondary line underneath.
  - **Expandable sections** (job description, analysis panels): collapsed by default,
    a text link or chevron button to reveal.

---

## 3. Job detail modal

Opened from a job title, in Search results or Pipeline's Jobs sub-tab — identical either
way.

1. **Header:** grade tile + score % (e.g. green "A 90%") on the left, job title (bold,
   larger) and company name beneath it.
2. **Meta grid** (2–3 columns of label/value pairs): Location · Salary · Portal ·
   Category · Employment type · Education · Start timeline · Deadline · Posted date ·
   Job ID. If the raw salary text differs from the parsed value, show it as a small
   secondary line under Salary.
3. **Contacts** line, if any contact text came with the posting.
4. **Skills** — chip row.
5. **Description** — collapsed by default; two toggle buttons above it, **Translate**
   and **Compact**, that reveal/reformat the text when clicked.
6. **Match rationale** — one italic/muted line explaining why this job matched.
7. **Analysis panels** (each collapsed, loads on click): Salary chart (bar/range chart
   against market data for that category), Quality assessment, Candidate-Strength
   assessment.
8. **AI chat thread** — a small chat-bubble UI further down the modal, scoped to this one
   job (ask follow-up questions about it).
9. **Footer:** Save button — clicking reveals an inline notes field + status dropdown;
   an "Open posting" external-link button alongside it.

## 4. Candidate detail modal

Opened from a candidate name, in Saved candidates or Pipeline's Kandidaten sub-tab.

1. **Header:** candidate name (bold, large), a status badge (pipeline stage — New /
   Contacted / Interviewing / Placed / Rejected), "saved by <owner>" caption, and a match
   count badge. Inline **Edit** toggle on this header block.
2. **Contact line:** email, phone, LinkedIn — small icon-links.
3. **Fact chips:** Industry, Role category, Languages, Salary expectation, Availability.
4. **Summary** — an AI-generated paragraph describing the candidate.
5. **Skills** — chip row.
6. **Experience** — list rows (title / company, with a date-range secondary line), up to
   8 entries.
7. **Education** — list rows, up to 6 entries.
8. **Certifications** — chip row.
9. **Matched jobs** — a compact table/list: grade tile, job title, company, location,
   salary, and pipeline status per row. Each opens the Job detail modal (§3) on click.

## 5. Company detail panel

Opened from a company name, in the Companies collection ("My saved" — not Browse-market
rows, which stay lightweight name + Save only) or Pipeline's Unternehmen sub-tab.

1. **Header:** company name (bold, large), Save button, a subtitle line (job count +
   primary location).
2. **Stat row:** three side-by-side stat cards — active jobs count, average salary,
   number of states/regions the company posts in.
3. **AI hiring-profile summary** — a generated paragraph describing the company's hiring
   patterns.
4. **Top roles** and **top sectors** — two short ranked lists side by side.
5. **Salary range** — a compact min–max display.
6. **Active locations** — a short list/chip row of cities/regions.
7. **Recent postings** — list rows (title, date, location).
8. **Contacts** — list of known contacts at this company, each row with its own inline
   Save button; clicking a contact name opens the Contact detail modal (§6).

## 6. Contact detail modal

Opened from a contact name, in the Contacts collection ("My saved") or Pipeline's Kontakte
sub-tab.

1. **Header:** contact name (bold, large), title, company name beneath it.
2. **Contact info:** email, phone, LinkedIn — icon-links.
3. **Location**, **saved date**, and a free-text **notes** field (editable inline).
4. **Jobs** section (loads async, shows a small spinner first): list rows of postings
   associated with the contact's company — title, city, salary, portal, posted date —
   each linking out to the original posting.

---

## 7. Sample content (for populating the mockup)

- **Job:** "Data Engineer (m/w/d)" — Anexia Cloud Solutions GmbH — Klagenfurt, Bezirk
  Innere Stadt, Kärnten — €56,000/mo — AMS portal — grade A 90% — description placeholder:
  "Design and maintain ETL pipelines, own our Python-based data infrastructure..." —
  match rationale: "Strong match: Python, ETL, SQL, automation and LLM/AI skills."
- **Candidate:** "Lukas Berger" — Python Developer (Web Scraping & Data) — Bratislava —
  status New — 3 matched jobs — skills: Python, Selenium, SQL, ETL, Docker.
- **Company:** "Anexia Cloud Solutions GmbH" — Klagenfurt, Kärnten — 4 active jobs — avg
  salary €54,500 — top roles: Data Engineer, DevOps Engineer — contact: Maria Mayer.
- **Contact:** "Maria Mayer" — HR Manager — Anexia Cloud Solutions GmbH —
  mayer@inter.com — 0901/123123 — 2 associated postings.
