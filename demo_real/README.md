# Jobs Intelligence AI — Demo (Real DB)

Flask web app with live MySQL connection and simulated AI matching.

## Prerequisites

- Python 3.10+
- Network access to the AWS RDS instance (run from Windows, not WSL)

## Setup

```bash
cd demo_real
pip install -r requirements.txt
```

The `.env` file already contains the DB credentials. If you need to override:

```
DATABASE_URL=mysql+pymysql://USER:PASSWORD@HOST:PORT/Jobs_Intelligence_Austria
FLASK_DEBUG=true
FLASK_PORT=5000
```

## Run

```bash
python app.py
```

Then open: **http://localhost:5000**

## First startup — verify DB columns

Open **http://localhost:5000/debug/schema** in your browser.
This returns the actual column names from `View_Jobs_Full`.

Compare them to the `COL` mapping in `config.py` and update any that differ, e.g.:

```python
COL = {
    "job_id":    "JobID",        # ← change to match actual column name
    "title":     "JobTitle",
    ...
}
```

## Project structure

```
demo_real/
├── app.py              # Flask routes
├── config.py           # DB URL, column mapping, thresholds
├── requirements.txt
├── .env                # credentials (do not commit)
├── .env.example        # template
├── core/
│   ├── database.py     # SQLAlchemy engine, filter queries, job fetch
│   └── matching.py     # Simulated scoring (swap for real embeddings later)
└── templates/
    └── index.html      # Single-page app (Search / Saved / Map tabs)
```

## Upgrading to real AI matching

When ready to add real OpenAI vector search, replace the body of
`core/matching.py → score_jobs()` with:

1. Embed `candidate_text` using `text-embedding-3-small`
2. Retrieve top-N job vectors from the OpenAI Vector Store by cosine similarity
3. Return matched job IDs + similarity scores

The rest of the pipeline (DB fetch, API, frontend) stays unchanged.
