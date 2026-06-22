# Frontend Design — index.html

## Structure

Single HTML file, no build step. All JS is inline at the bottom of the file.
CSS is in a `<style>` block in `<head>`.

---

## Tab Layout

```
[ Search ] [ Chat ] [ Map ] [ Saved jobs ]
```

Each tab is a `.tab-panel` div. Switching tabs adds/removes the `.active` class.
The `Saved jobs` tab badge shows a live count of saved items.

---

## Search Tab

### Filter bar
Single row of functional filters — all wired to the `/api/match` API:

```
State (dropdown) | City (text) | Keywords (text) | Category (dropdown) | Portal (dropdown)
```

Populated on page load via `/api/filters`.

### Input modes
Three modes for entering a candidate profile, selected via `.mode-tab` buttons:

| Mode    | Element            | What it sends                          |
|---------|--------------------|----------------------------------------|
| CV      | textarea + file    | Raw CV text (PDF parsed client-side)   |
| Free    | textarea           | Plain natural language description     |
| Guided  | Grid of inputs     | Assembled into a structured text blob  |

`buildCandidateText()` reads the active mode and returns a single string.

### Results table
Columns: Score · Job title (clickable) · Company · Location · Salary · Portal · Posted · Actions

Clicking a job title calls `openJobModal(storeId)`.
The Actions column has a Save button and an external link icon.

---

## Chat Tab

```
┌─ toolbar: "AI recruiter assistant" ─────────── [New conversation] ─┐
│                                                                      │
│  [AI bubble] Hello! I'm your...                                      │
│                                                                      │
│  [User bubble] Find IT jobs in Vienna                                │
│                                                                      │
│  [AI bubble] Found 8 matching positions...                           │
│  ┌──────────────────────────────┐                                    │
│  │ A  87%  Software Developer   │  ← clickable → opens modal        │
│  │  Siemens · Vienna · €4,200   │                                    │
│  └──────────────────────────────┘                                    │
│  [ Load 8 jobs into results → ]                                      │
│                                                                      │
│  [ quick chips: Forklift Vienna · IT & Dev · ... ]                  │
├── [type message…] ────────────────────────── [Send] ───────────────┤
```

Chat messages are appended to `#chatThread`. The AI response is parsed by
`_parse()` in `chat.py` to split plain text from a trailing `json` block
containing the job array.

---

## Job Store Pattern

Job data is never serialised into HTML attributes (avoids quote-escaping bugs).
Instead, every job object is stored in a JS `Map` and referenced by a short ID:

```javascript
const _jobStore = new Map();      // 'jb1' → { title, salary, skills_en, ... }
let _jobStoreSeq = 0;

function storeJob(job) {
    const id = 'jb' + (++_jobStoreSeq);
    _jobStore.set(id, job);
    return id;                    // returned ID goes into onclick="openJobModal('jb1')"
}
```

Jobs are tagged with `_batch` when stored:
- Search results → `_batch: 'search'`
- Chat cards     → `_batch: 'chat'`

This lets the modal know which batch array to use for the salary overlay chart.

---

## Job Detail Modal

Opened by `openJobModal(storeId)`. Sections rendered dynamically:

```
┌─────────────────────────────────────────────────────────┐
│  [ A ] 87%  — Strong match              [ × close ]     │
│  Software Developer                                      │
│  Siemens AG                                              │
├─────────────────────────────────────────────────────────┤
│  Location      Salary       Portal                       │
│  Wien          €4,200       AMS                          │
│  Category      Posted       Job ID                       │
│  IT Dev...     2026-05-20   84291                        │
├── Skills ───────────────────────────────────────────────┤
│  [Python] [SQL] [Docker] [Agile] [Git] ...              │
├── Description ──────────────────────────────────────────┤
│  We are looking for a senior software developer...       │
├── Salary analysis — Softwareentwickler ─────────────────┤
│  [Plotly histogram — see SALARY_ANALYSIS.md]             │
│  Sample: 312 jobs · Mean: €3,800 · Median: €3,500        │
│  This job: €4,200 (+€400 vs mean · top 62%)             │
├─────────────────────────────────────────────────────────┤
│  [+ Save to pipeline] [New ▾]     [Open posting ↗]      │
└─────────────────────────────────────────────────────────┘
```

Skills are parsed from `job.skills_en` (comma-separated string from DB).
The salary analysis section is only shown when `job.occ_group` is set.

---

## Saved Jobs Tab

Jobs are grouped by `candidate_name` (entered in the candidate bar before saving).

```
┌─ Saved Pipeline  [3] ───────────────────────────────────┐
│                                                          │
│  Jan Novak          3 jobs   [A×2] [B×1]                │
│  ┌────────────────────────────────────────────────────┐ │
│  │ A  Software Dev  · Wien  · €4,200  [New ▾]  [↗][✕]│ │
│  │ A  Backend Eng   · Graz  · —       [New ▾]  [↗][✕]│ │
│  │ B  DevOps Eng    · Wien  · €3,800  [New ▾]  [↗][✕]│ │
│  └────────────────────────────────────────────────────┘ │
│                                                          │
│  Maria Hofer        1 job    [B×1]                       │
│  ...                                                     │
└──────────────────────────────────────────────────────────┘
```

Pipeline statuses: `New · Contacted · Placed · Rejected`
Each status has a distinct colour class: `.s-New`, `.s-Contacted`, etc.

---

## State Variables

| Variable        | Type          | Purpose                                         |
|-----------------|---------------|-------------------------------------------------|
| `lastResults`   | `array`       | Jobs from the last Search run                   |
| `savedJobs`     | `array`       | Mirror of server `_saved_jobs`                  |
| `chatLastJobs`  | `array`       | Jobs from the last Chat AI response             |
| `_modalJob`     | `object`      | Job currently open in the modal                 |
| `_jobStore`     | `Map`         | storeId → full job object                       |
| `SESSION_ID`    | `string`      | Random ID for chat session continuity           |
| `sortCol/Asc`   | `string/bool` | Current sort state for results table            |
| `leafletMap`    | `object`      | Leaflet map instance (lazy init)                |
