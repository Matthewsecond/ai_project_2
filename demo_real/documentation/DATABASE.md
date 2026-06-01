# Database Design

## Connection

AWS RDS MySQL instance.
Connection string in `.env` as `DATABASE_URL`.
SQLAlchemy `QueuePool` with pool_size=5, max_overflow=10.

```
Host:   REDACTED-DB-HOST
Port:   9906
DB:     Jobs_Intelligence_Austria
```

---

## Primary View: `View_Jobs_Full`

The application reads exclusively from this view. Column mapping in `config.COL`:

| Config key   | DB column            | Description                          |
|--------------|----------------------|--------------------------------------|
| `job_id`     | `id`                 | Primary key                          |
| `title`      | `position`           | Job title                            |
| `company`    | `company`            | Employer name (from crawler)         |
| `description`| `description`        | Full text description (often null)   |
| `state`      | `state`              | Austrian Bundesland                  |
| `city`       | `city`               | City + district                      |
| `salary`     | `salary`             | Monthly salary as string (often null)|
| `url`        | `cleaned_link`       | Job posting URL                      |
| `portal`     | `portal`             | Source: ams / karriere / stepstone   |
| `occ_group`  | `occupational_group` | Occupational category (AMS taxonomy) |
| `esco_skills`| `esco_skills`        | ESCO skill tags (from enrichment)    |
| `date_posted`| `date_posted`        | Originally `publication_date`        |
| `lat`        | `latitude`           | Latitude (if geocoded)               |
| `lon`        | `longitude`          | Longitude (if geocoded)              |
| `status`     | `status`             | new / updated / outdated             |
| `skills`     | `skills`             | Comma-separated skills (original)    |
| `skills_en`  | `skills_english`     | Comma-separated skills (English)     |

Additional columns present in the view (not yet used in the app):
- `employment_relationship` — e.g. "ArbeiterInnen/Angestellte"
- `work_time` — e.g. "Vollzeit", "Teilzeit/Vollzeit"
- `contract_type` — e.g. "permanent", "temporary"
- `education` — required education level
- `summary` — LLM-generated summary
- `contacts` — recruiter contact info

---

## Salary Data Quality

Salary coverage is partial. Many rows have `salary = NULL`.
For the salary analysis, meaningful data exists for:
- Blue-collar categories (LagerarbeiterIn, Koch, RaumpflegerIn, etc.)
- Some white-collar categories (IT, healthcare)

Salary values are stored as plain numbers ("2400") representing monthly EUR.
Some outliers exist (annual salaries stored in the same field).
The `/api/salary_stats` endpoint filters `< €200` and trims top 2%.

---

## Skills Data (Slovakia DB)

The Slovakia database (`Jobs_Intelligence_Slovakia`) has a richer skills schema:

```
skills                    — id, skill (SK), skill_english (EN), canonical_skill_en
skill_jobs_junction       — job_id, skill_id, skill_type
View_Skills               — flattened view joining jobs + skills
```

The Austria DB stores skills as comma-separated strings directly on the job record
(`skills`, `skills_english` columns in `View_Jobs_Full`).

---

## Query Patterns

### Fetch by IDs (post vector-search)
```sql
SELECT *
FROM View_Jobs_Full
WHERE id IN (:id_0, :id_1, :id_2, ...)
```

### Fetch with filters (keyword fallback)
```sql
SELECT *
FROM View_Jobs_Full
WHERE state         = :state
  AND occupational_group = :occ_group
  AND portal        = :portal
  AND city          LIKE :city          -- %value%
  AND (position LIKE :pos_0 OR ...)     -- _positions fallback
LIMIT :limit
```

### Salary distribution
```sql
SELECT CAST(salary AS DECIMAL(10,2)) AS sal
FROM View_Jobs_Full
WHERE occupational_group = :occ
  AND salary IS NOT NULL
  AND salary != ''
  AND CAST(salary AS DECIMAL(10,2)) > 200
LIMIT 1000
```

---

## Vector Store

OpenAI Vector Store ID: `vs_69ef6c6e9ef88191b08dc04ef28cf76e`

Jobs are indexed as text documents in the vector store.
The `file_search` tool is used by both matching and chat to retrieve semantically
relevant jobs given a candidate query.

The matching flow:
1. Model reads file_search results and extracts job IDs + titles
2. App resolves IDs against MySQL to get full records
3. MySQL is the source of truth for all structured data (salary, location, etc.)

The vector store and MySQL can drift if jobs are added/removed from one but not the other.
Jobs found in the vector store but missing from MySQL are returned with minimal data
(title only, no salary/location/skills).

---

## Running Schema Check

On first deployment or after DB changes:
```
GET http://localhost:5000/debug/schema
```
Compare returned column names against `config.COL` and update the mapping if needed.
