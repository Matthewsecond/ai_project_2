# Jobs Intelligence AI — Documentation

This folder **mirrors the package** `src/jobs_intelligence_ai/` — one doc folder per
module (foundation / services / frontend), same convention as the `tests/` tree. Empty
module folders hold a `.gitkeep` until they're documented. Cross-cutting and planning
docs live at the top level.

## Top-level

| Doc | Contents |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System overview, stack, data flow, key design decisions |
| [TESTING.md](TESTING.md) | Test layout, tiers, how to run, current inventory |
| [planning/](planning/) | **All plans live here** — see [planning/README.md](planning/README.md) for what's active vs deferred vs archived |

## Per-module (mirrors `src/jobs_intelligence_ai/`)

| Module | Docs |
|---|---|
| `config/` | _(to document)_ |
| `infra/` | [DATABASE.md](infra/DATABASE.md) — view column mapping, salary data quality, query patterns |
| `shared/` | [README.md](shared/README.md) — foundation layer; `llm` (single OpenAI client), and json/job/grading/taxonomy as 2.1 lands them |
| `services/search/` | _(to document — see ARCHITECTURE.md for now)_ |
| `services/stats/` | [SALARY_ANALYSIS.md](services/stats/SALARY_ANALYSIS.md) — two-layer chart design, Plotly traces, edge cases |
| `services/interview/` | [INTERVIEW_REWORK_CHANGELOG.md](services/interview/INTERVIEW_REWORK_CHANGELOG.md) |
| `services/` (enrichment, reporting, chat, clustering, candidate, geo, auth) | _(to document)_ |
| `frontend/` | [API.md](frontend/API.md) — Flask endpoints, request/response shapes · [FRONTEND.md](frontend/FRONTEND.md) — tab layout, job store, modals, chat UI |

> Note: folder names track the **target** structure from RESTRUCTURE_PLAN.md. Some code
> still lives at its pre-rework path until the corresponding Stage 2 step lands; the docs
> lead the move so the end state is documented up front.

## Running locally

```bash
pip install -e .
cp .env.example .env      # fill in OPENAI_API_KEY and DATABASE_URL[_SK]
python -m jobs_intelligence_ai        # or: python -m jobs_intelligence_ai --sk
```

Open: http://localhost:5000 · Schema debug: http://localhost:5000/debug/schema
