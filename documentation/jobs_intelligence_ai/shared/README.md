# shared/ — foundation layer

Reusable code + domain helpers used across the app. **A service may import from
`shared`; `shared` never imports a service or the frontend.** Built up over rework
Stage 2.1 by consolidating code that was duplicated or trapped in the wrong module.

## Modules

| Module | Purpose | Status |
|---|---|---|
| `llm.py` | The single app-wide OpenAI client (`get_client()` singleton). | ✅ 2.1a |
| `json.py` | LLM-response JSON extraction (array + fenced object) + citation stripping. | ⏳ 2.1b |
| `job.py` | Canonical job dict: field map + `serialize_job` / `overlay_job`. | ⏳ 2.1c |
| `grading.py` | `grade()` score → A/B/C banding. | ⏳ 2.1d |
| `taxonomy.py` | Sector/role taxonomy for the funnel. | ⏳ 2.1e |

## `llm.py`

```python
from jobs_intelligence_ai.shared.llm import get_client
client = get_client()          # lazily-created singleton; defaults to config.OPENAI_API_KEY
```

One place constructs the OpenAI client, so there's a single seam to mock in tests
(`monkeypatch` `shared.llm.OpenAI` or `get_client`). Replaces the two previous client
paths — `chat._get_client` (now a shim re-exporting this) and the standalone
`OpenAI(...)` that `search/orchestrator` used to build.

Tests: `tests/jobs_intelligence_ai/shared/unit_tests/test_5_llm.py`.
