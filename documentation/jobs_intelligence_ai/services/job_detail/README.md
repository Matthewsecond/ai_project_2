# services/job_detail/

The one-shot AI tools behind the **Job Detail modal** — the model calls a recruiter triggers from
a single, already-retrieved job card. Packaged in rework Stage 2.4 by relocating the five inline
LLM calls out of the `job_detail` blueprint. (The single-job *chat* is separate — it lives in
`services/search/job_chat`; this package is the stateless one-shot tools.)

## Layout
```
services/job_detail/
├── __init__.py       # public API
├── config.py         # the five tools' prompts + Structured-Outputs schemas
└── operations.py     # the five tool functions (4 prose + 1 JSON)
```

## Public API
```python
from jobs_intelligence_ai.services.job_detail import (
    translate_description, compact_description, generate_cv_questions,
    write_outreach, score_candidate_strength,
)
```
Consumer: the `job_detail` blueprint (Job Detail modal).

## Structured-Outputs status (2.4)
All five calls were inline `responses.create` in the blueprint; each is now a service function
on the shared `shared.llm.get_client`, and every call uses `responses.parse`:
- ✅ **translate_description** — English translation → single-field `JobDetailText`.
- ✅ **compact_description** — 3-4 sentence summary → `JobDetailText` (`lang="en"` adds an English note).
- ✅ **generate_cv_questions** — gap-based interview questions from job + CV → `JobDetailText`.
- ✅ **write_outreach** — candidate outreach message from job + name + CV → `JobDetailText`.
- ✅ **score_candidate_strength** — 5-dimension fit score → `CandidateStrength` (parallel
  `axes`/`scores`/`reasons` + `overall`). This is the one **real-JSON** call: it replaces the
  blueprint's "Return ONLY valid JSON" prompt + fence-strip + `json.loads` — the **last such
  hand-parse in a blueprint**.

Every tool raises on no API key / model error (the blueprint maps that to a 500); the blueprint
thinned to validate-input → call-service → jsonify. The four prose tools share `JobDetailText`
(single `text` field). Input lengths are capped in `operations.py` to mirror the old slicing.

## Tests
`tests/jobs_intelligence_ai/services/job_detail/unit_tests/test_1_operations` (8, offline): each
prose tool returns the model text + grounds its inputs (English note only for `lang="en"`),
candidate-strength returns a dict with the 5 dimensions in order, and no-key / model-error / null
parse all raise. `smoke_tests/test_job_detail_smoke` (3, live-asserting): translate, compact,
candidate-strength (five in-range scores + reasons + overall).
