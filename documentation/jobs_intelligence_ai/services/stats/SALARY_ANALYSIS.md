# Salary Analysis — Design & Implementation Plan

## Goal

When a recruiter opens any job in the modal, show a visual salary analysis:
- Where does this job sit relative to the broader market for its category?
- How does it compare to the other jobs returned in the same search/chat?

---

## Two-Layer Reference Group (Option D)

The chart combines two data sources rendered as separate Plotly traces:

```
Layer 1 — Market background (DB query)
  Source:  GET /api/salary_stats?occ_group=Softwareentwickler
  Data:    Up to 1000 salary values from View_Jobs_Full for that occupational group
  Visual:  Grey histogram (background distribution)

Layer 2 — Current batch overlay (in-memory, no API call)
  Source:  lastResults  (if job._batch === 'search')
        or chatLastJobs (if job._batch === 'chat')
  Data:    Salary of each job in the current search/chat result set
  Visual:  Coloured dots on the x-axis (rug plot), colour = grade A/B/C

Layer 3 — This job (highlighted)
  Source:  _modalJob.salary
  Visual:  Navy diamond on the x-axis, annotation callout
```

---

## Chart Anatomy

```
count
  │
  │         ░░░                         ← Layer 1: DB histogram
  │       ░░░░░░░                          grey bars, market distribution
  │     ░░░░░░░░░░░░
  │   ░░░░░░░░░░░░░░░░
  │     ░░░░░░░░░░░░░░░
  │       ░░░░░░░░░░░
  │         ░░░░░░
  │           ░░
  └────┬──────┬────────────────── EUR
       │      │   ●  ●  ◆  ●     ← Layer 2: batch dots (on y=0)
       │      │                     ◆ = this job (navy diamond)
   median  mean                     ● = other batch jobs (grade colour)
  (purple) (amber)
  dashed   dashed
```

---

## Data Flow

```
openJobModal(storeId)
        │
        ├── job = _jobStore.get(storeId)
        │
        ├── batchJobs = job._batch === 'chat'
        │               ? chatLastJobs
        │               : lastResults
        │
        └── loadSalaryAnalysis(job, batchJobs)
                    │
                    ├── [async] fetch /api/salary_stats?occ_group={job.occ_group}
                    │               ↓
                    │           dbData = { salaries[], mean, median, count }
                    │
                    ├── [sync]  batchPoints = batchJobs
                    │               .filter(j => parseable salary)
                    │               .map(j => ({ sal, title, grade }))
                    │
                    └── Plotly.react('modalAnalysisChart', [
                                trace0: histogram  ← dbData.salaries
                                trace1: scatter    ← batchPoints  (rug)
                                trace2: scatter    ← [jobSalary]  (this job)
                            ], layout)
```

---

## Job Batch Tagging

Jobs must be tagged at storage time so the modal knows which batch array to use.

**In `renderResults()` (search tab):**
```javascript
const sid = storeJob({ ...job, _batch: 'search' });
```

**In `appendAiMessage()` (chat tab):**
```javascript
const sid = storeJob({ ...normalized, _batch: 'chat' });
```

---

## Plotly Trace Definitions

### Trace 0 — Market histogram
```javascript
{
    type:    'histogram',
    x:       dbData.salaries,
    name:    'Market distribution',
    marker:  { color: '#dde8f4', line: { color: '#99b8f0', width: 0.5 } },
    opacity: 0.7,
    hovertemplate: '%{y} jobs at ~€%{x}<extra></extra>',
}
```

### Trace 1 — Batch rug plot
```javascript
{
    type:        'scatter',
    mode:        'markers',
    x:           batchPoints.map(p => p.sal),
    y:           batchPoints.map(() => 0),
    text:        batchPoints.map(p => p.title),
    name:        'This search',
    marker: {
        size:    10,
        symbol:  'circle',
        color:   batchPoints.map(p =>
                     p.grade === 'A' ? '#1a7a2e' :
                     p.grade === 'B' ? '#e8a800' : '#aaa'),
        line:    { width: 1.5, color: '#fff' },
    },
    hovertemplate: '<b>%{text}</b><br>€%{x}<extra></extra>',
}
```

### Trace 2 — This job
```javascript
{
    type:   'scatter',
    mode:   'markers',
    x:      [jobSalary],
    y:      [0],
    name:   'This job',
    marker: { size: 14, symbol: 'diamond', color: '#1a3864',
              line: { width: 2, color: '#fff' } },
    hovertemplate: '<b>This job</b><br>€%{x}<extra></extra>',
}
```

### Shapes (reference lines)
```javascript
shapes: [
    { type:'line', x0: data.mean,   x1: data.mean,   y0:0, y1:1,
      xref:'x', yref:'paper', line:{ color:'#e8a800', width:2, dash:'dot' } },
    { type:'line', x0: data.median, x1: data.median, y0:0, y1:1,
      xref:'x', yref:'paper', line:{ color:'#a78bfa', width:2, dash:'dot' } },
]
```

---

## Backend: `/api/salary_stats`

```
GET /api/salary_stats?occ_group=Softwareentwickler

SQL:
    SELECT CAST(salary AS DECIMAL(10,2)) AS sal
    FROM View_Jobs_Full
    WHERE occupational_group = :occ
      AND salary IS NOT NULL
      AND salary != ''
      AND CAST(salary AS DECIMAL(10,2)) > 200
    LIMIT 1000

Post-processing (Python):
    - Remove top 2% outliers (annual salaries mixed in)
    - Compute mean and median via statistics module

Response:
    {
        "ok":       true,
        "count":    312,
        "salaries": [1800, 2100, 2400, ...],   ← raw array for histogram
        "mean":     3247,
        "median":   3100
    }
```

---

## Stats Row Below Chart

```
Sample          Group mean     Group median     This job
312 jobs        €3,247         €3,100           €4,200 (+€953 vs mean · top 71%)
```

The "top X%" is computed client-side:
```javascript
const pctBelow = Math.round(
    (data.salaries.filter(s => s < jobSalary).length / data.count) * 100
);
// "top 29%" = 100 - 71
```

---

## Edge Cases

| Situation                              | Behaviour                                      |
|----------------------------------------|------------------------------------------------|
| `occ_group` is null                   | Analysis section hidden entirely               |
| DB has no salary data for that group  | "No salary data available" message             |
| Job's own salary is null              | Traces 0+1 still render; trace 2 omitted       |
| Batch has no salaries                 | Trace 1 omitted; only DB histogram shown       |
| Salary is non-numeric string          | `parseFloat` returns NaN → filtered out        |
| Modal closed before fetch completes   | Plotly call targets detached div → no-op       |
