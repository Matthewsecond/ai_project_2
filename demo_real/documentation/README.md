# Jobs Intelligence Austria — Documentation

## Documents

| File                   | Contents                                                      |
|------------------------|---------------------------------------------------------------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System overview, stack, directory layout, data flow, key design decisions |
| [FRONTEND.md](FRONTEND.md)         | Tab layout, job store pattern, modal sections, state variables, chat UI   |
| [API.md](API.md)                   | All Flask endpoints — request/response shapes, matching pipeline          |
| [DATABASE.md](DATABASE.md)         | View_Jobs_Full column mapping, salary data quality, query patterns        |
| [SALARY_ANALYSIS.md](SALARY_ANALYSIS.md) | Two-layer chart design (Option D), Plotly traces, data flow, edge cases  |

---

## Feature Status

| Feature                          | Status        |
|----------------------------------|---------------|
| Search tab + AI matching         | Done          |
| Keyword fallback (no API key)    | Done          |
| Filter bar (State/City/Category/Portal) | Done    |
| Chat tab (multi-turn)            | Done          |
| Map tab (Leaflet)                | Done          |
| Saved jobs (grouped by candidate)| Done          |
| Job detail modal                 | Done          |
| Skills display in modal          | Done          |
| Salary analysis — DB histogram   | Done          |
| Salary analysis — batch overlay  | Planned (see SALARY_ANALYSIS.md) |
| Export CSV                       | Done          |
| Candidate name field             | Done          |

---

## Next Implementation: Salary Chart Batch Overlay

The salary analysis chart currently shows only the DB market distribution.
The next step adds a second layer: the jobs from the current search/chat result
as individual dots coloured by grade (A/B/C), so the recruiter can see where
tonight's specific results sit within the broader market.

See [SALARY_ANALYSIS.md](SALARY_ANALYSIS.md) for the full design.

Required code changes (all in `index.html`):
1. Tag jobs with `_batch: 'search'` or `_batch: 'chat'` when calling `storeJob()`
2. Pass `batchJobs` to `loadSalaryAnalysis(job, batchJobs)` from `openJobModal()`
3. Add trace 1 (batch rug) and trace 2 (this job diamond) to `Plotly.react()`

---

## Running Locally

```bash
cd demo_real
pip install -r requirements.txt
cp .env.example .env      # fill in OPENAI_API_KEY and DATABASE_URL
python app.py
```

Open: http://localhost:5000
Schema debug: http://localhost:5000/debug/schema
