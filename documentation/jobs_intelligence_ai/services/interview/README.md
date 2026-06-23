# services/interview/

Live interview scoring for the job-detail modal. `InterviewHelper` owns the whole
interview loop for one (candidate, job) pair — generate gap-based questions, score each
recorded answer as the exchange unfolds, suggest follow-ups, and roll the answers up into
an overall recommendation — plus candidate-facing coaching and a running per-aspect read.
Packaged from the single `interview_helper.py` file in rework Stage 2.3 #3.

## Layout
```
services/interview/
├── __init__.py       # public API → InterviewHelper
├── config.py         # model + prompt building blocks (rubric/calibration/lang) + per-call
│                     #   prompts + the Structured-Outputs Pydantic schemas
└── orchestrator.py   # InterviewHelper class + prompt-assembly & output-shaping helpers
```

## Public API
```python
from jobs_intelligence_ai.services.interview import InterviewHelper
```
Consumer: `web/blueprints/interview.py` (thin wrappers over the helper; the interview
RECORD is persisted by the front-end into the saved job's `extras.interview`).

`InterviewHelper` methods: `generate_questions`, `parse_questions`, `analyze_answer`,
`suggest_followup`, `summarize`, `model_answer`, `improvement_opportunities`,
`assess_candidate`, plus `preview_context` (the "what the AI sees" panel — no model call).
Every method degrades to `{"ok": False, "error": …}` instead of raising, so a flaky model
call never 500s the interview UI.

## Structured-Outputs status (2.3 #3)
All eight model calls were converted to Structured Outputs:
`responses.parse(text_format=<schema>)` → validated `output_parsed`, via
`shared.llm.get_client`. The hand-rolled `_parse_json` (fence/embedded-JSON parser) is
**deleted**, and the "Return ONLY valid JSON in this exact shape: {…}" boilerplate is gone
from every prompt — the schema enforces the shape instead.

| Call | Schema (`config.py`) |
|---|---|
| `generate_questions` | `QuestionList` |
| `parse_questions` | `ParsedQAList` |
| `analyze_answer` | `AnswerAnalysis` (nullable `score`; `Literal` status) |
| `suggest_followup` | `Followup` |
| `summarize` | `InterviewSummary` |
| `model_answer` | `ModelAnswer` |
| `improvement_opportunities` | `OpportunityList` (`Literal` impact) |
| `assess_candidate` | `AspectAssessment` (`Literal` status) |

The `_coerce_*` post-processing helpers are kept: Structured Outputs guarantees the
*shape*, but these still enforce the value bounds and interview-specific rules the schema
can't express — score clamping to 0–100, the `final` override (force a score even when the
model judged the exchange incomplete), follow-up exhaustion on an empty question, and list
caps. Prompts + schemas live in `config.py`.

## Tests
`tests/jobs_intelligence_ai/services/interview/unit_tests/test_1_interview.py` (18, offline)
— inject a fake client and assert the post-processing rules + the input guards and the
no-key / API-failure / `output_parsed is None` fallbacks. `smoke_tests/test_interview_smoke.py`
(2, live-asserting) — generate questions and score a strong answer against the real API.

See [INTERVIEW_REWORK_CHANGELOG.md](INTERVIEW_REWORK_CHANGELOG.md) for the feature history
(the 2026-06-19 scorecard rework, predating this repackaging).
