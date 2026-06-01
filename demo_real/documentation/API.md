# API Reference

Base URL: `http://localhost:5000`

---

## GET `/`
Returns the main SPA (`index.html`).

---

## GET `/api/filters`
Returns distinct dropdown values for the filter bar.

**Response:**
```json
{
    "ok": true,
    "data": {
        "states":     ["Wien", "Niederösterreich", ...],
        "occ_groups": ["Softwareentwickler", "LagerarbeiterIn", ...],
        "portals":    ["ams", "karriere", "stepstone", ...]
    }
}
```

---

## POST `/api/match`
Runs AI vector matching for a candidate profile.

**Request:**
```json
{
    "candidate_text": "Senior Python developer, 5 years experience, Vienna...",
    "filters": {
        "state":     "Wien",
        "occ_group": "Softwareentwickler",
        "portal":    "ams",
        "city":      "Wien"
    },
    "top_n": 20
}
```
All filter fields are optional. `top_n` defaults to 20, max 50.

**Response:**
```json
{
    "ok":    true,
    "count": 15,
    "top_n": 20,
    "jobs": [
        {
            "job_id":       "84291",
            "title":        "Software Developer",
            "company":      "Siemens AG",
            "state":        "Wien",
            "city":         "Wien",
            "salary":       "4200",
            "url":          "https://...",
            "portal":       "ams",
            "occ_group":    "Softwareentwickler",
            "posted":       "2026-05-20",
            "lat":          48.2082,
            "lon":          16.3738,
            "skills":       ", Python, Docker, SQL",
            "skills_en":    ", Python, Docker, SQL",
            "score":        0.87,
            "score_pct":    "87%",
            "grade":        "A",
            "match_reason": "Strong Python and cloud skills match"
        }
    ]
}
```

**Matching pipeline:**
1. OpenAI Responses API with `file_search` on vector store
2. Model returns `[{ job_id, position, score, match_reason }]`
3. IDs resolved against MySQL `View_Jobs_Full`
4. Unresolved IDs retried via position-name `LIKE` query
5. Hard filters applied; results sorted by score

**Fallback:** If no OpenAI key, Jaccard keyword similarity is used instead.

---

## GET `/api/saved`
Returns all saved pipeline jobs.

**Response:**
```json
{
    "ok":    true,
    "count": 3,
    "jobs":  [ { ...job fields..., "pipeline_status": "New", "notes": "", "candidate_name": "Jan Novak" } ]
}
```

---

## POST `/api/saved`
Adds a job to the pipeline.

**Request:**
```json
{
    "job":    { ...full job object... },
    "status": "New"
}
```
Duplicate `job_id` is silently ignored.

**Response:** Same as `GET /api/saved`.

---

## PATCH `/api/saved/<job_id>`
Updates status or notes for a saved job.

**Request:**
```json
{ "pipeline_status": "Contacted" }
```
or
```json
{ "notes": "Called on Monday, interested" }
```

---

## DELETE `/api/saved/<job_id>`
Removes a job from the pipeline.

---

## POST `/api/chat`
Sends a chat message and returns AI response + any found jobs.

**Request:**
```json
{
    "session_id": "abc123",
    "message":    "Find IT developer jobs in Vienna"
}
```

**Response:**
```json
{
    "ok":   true,
    "text": "Found 8 matching positions in the IT sector in Vienna...",
    "jobs": [
        {
            "title":               "Software Developer",
            "company":             "Siemens AG",
            "city":                "Wien",
            "state":               "Wien",
            "salary":              "4200",
            "portal":              "ams",
            "occ_group":           "Softwareentwickler",
            "description_snippet": "We are looking for a senior developer...",
            "score":               0.87
        }
    ]
}
```

`jobs` is empty if the AI found no relevant postings or the query was not job-search related.

**Multi-turn memory:** The server maps `session_id → last_response_id`. Each request
passes `previous_response_id` to the Responses API so the model has full conversation history.

---

## POST `/api/chat/reset`
Clears conversation history for a session.

**Request:**
```json
{ "session_id": "abc123" }
```

---

## GET `/api/salary_stats`
Returns salary distribution for an occupational group.

**Query params:** `occ_group` (required)

**Example:** `/api/salary_stats?occ_group=Softwareentwickler`

**Response:**
```json
{
    "ok":       true,
    "count":    312,
    "salaries": [1800, 2100, 2250, 2400, 2600, 3000, 3200, 3500, 4200],
    "mean":     3247.0,
    "median":   3100.0
}
```

Salaries below €200 are excluded. Top 2% are trimmed to remove outliers
(annual salaries stored as monthly equivalents, etc.).

Returns `{ count: 0, salaries: [] }` if no salary data exists for that group.

---

## GET `/debug/schema`
Returns `DESCRIBE View_Jobs_Full` — useful for verifying column names after DB changes.

**Response:**
```json
{
    "ok": true,
    "columns": [
        { "Field": "id",           "Type": "int(11)",    ... },
        { "Field": "position",     "Type": "varchar(255)",...},
        { "Field": "salary",       "Type": "varchar(50)", ...},
        { "Field": "skills",       "Type": "text",        ...},
        { "Field": "skills_english","Type": "text",       ...},
        ...
    ]
}
```
