# Jobs Intelligence Austria — Architecture Overview

## System Summary

A Flask web application for recruitment agencies. Recruiters enter a candidate profile
(CV text, free-text, or guided form), the system finds matching job postings from a live
Austrian job database, and the recruiter saves matches into a candidate pipeline.

A conversational chat mode lets recruiters search the same database using natural language.

---

## Stack

| Layer       | Technology                                      |
|-------------|-------------------------------------------------|
| Backend     | Python 3.11 · Flask                             |
| Database    | AWS RDS MySQL · SQLAlchemy (QueuePool)          |
| AI matching | OpenAI Responses API · file_search tool         |
| Vector store| OpenAI Vector Store `vs_69ef6c6e9ef88191b08dc04ef28cf76e` |
| Frontend    | Vanilla JS · Leaflet.js (map) · Plotly (charts) |
| Styling     | Plain CSS (no framework) · warm beige design    |

---

## Directory Layout

```
demo_real/
├── app.py                  # Flask app, all route definitions
├── config.py               # Environment config, column name mapping
├── core/
│   ├── database.py         # SQLAlchemy engine, query helpers
│   ├── matching.py         # AI vector matching + keyword fallback
│   └── chat.py             # Multi-turn chat via Responses API
├── templates/
│   └── index.html          # Single-page app (all JS inline)
├── documentation/          # This folder
└── .env                    # API keys, DB URL (not committed)
```

---

## High-Level Data Flow

```
Recruiter browser
      │
      │  POST /api/match  { candidate_text, filters, top_n }
      ▼
  app.py  ──►  matching.py
                   │
                   ├─► OpenAI Responses API
                   │       file_search on Vector Store
                   │       returns: [{ job_id, position, score, match_reason }]
                   │
                   ├─► database.py  fetch_jobs_by_ids()
                   │       MySQL: SELECT * FROM View_Jobs_Full WHERE id IN (...)
                   │
                   └─► returns ranked job list to browser
                           [{ job_id, title, company, salary, skills, score, grade, ... }]

      │
      │  POST /api/chat  { session_id, message }
      ▼
  app.py  ──►  chat.py
                   │
                   └─► OpenAI Responses API (same vector store)
                           multi-turn via previous_response_id
                           returns: { text, jobs[] }

      │
      │  GET /api/salary_stats?occ_group=X
      ▼
  app.py  ──►  database.py
                   │
                   └─► MySQL: salary distribution for occupational group
                           returns: { salaries[], mean, median, count }
```

---

## Key Design Decisions

### Column name mapping (`config.COL`)
All SQL column references go through `config.COL` so if the DB view is renamed,
only one dict needs updating. Example:
```python
COL = {
    "job_id":    "id",
    "title":     "position",
    "occ_group": "occupational_group",
    "skills_en": "skills_english",
    ...
}
```

### Keyword fallback
If no OpenAI API key is set, `matching.py` falls back to Jaccard keyword similarity
computed entirely against the MySQL data. No AI dependency for basic demos.

### Candidate pipeline (MySQL-backed)
Saved jobs, candidate profiles, guided-builder specs, and an access audit trail
persist to the `Jobs_Intelligence_AI` schema via `helpers/candidate_store.py`
(tables: `candidate`, `candidate_saved_job`, `target_candidate`, `audit_log`).
Real-candidate personal data is GDPR-shaped: profiles/saved jobs are keyed by a
surrogate `candidate_id`, erasing a candidate cascades to their saved jobs, and
the audit log retains the id (no FK) so the trail survives erasure. The guided
builder's `target_candidate` specs are search templates, not personal data.

### Session continuity in chat
`chat.py` keeps a `_sessions` dict mapping `session_id → last_response_id`.
Each new chat turn passes `previous_response_id` to the Responses API so the
model has full conversation context without re-sending the whole history.
