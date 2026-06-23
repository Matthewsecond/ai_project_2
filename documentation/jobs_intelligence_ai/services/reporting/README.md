# services/reporting/

Turns saved insights / saved jobs into recruiter-facing briefings and polished PDF reports.
Three concerns grouped because they all produce reports. Packaged in rework Stage 2.3 #4.

## Layout
```
services/reporting/
├── __init__.py              # public API
├── config.py                # models + per-call prompts + Structured-Outputs schemas
├── opportunity_briefing.py  # LLM market briefing + AI filter suggestion (Radar tab)
├── report_generator.py      # Analytics session report: LLM elaboration + reportlab PDF
└── report_pipeline.py       # Candidate Pipeline / Match Insights PDFs (pure reportlab)
```

## Public API
```python
from jobs_intelligence_ai.services.reporting import (
    generate_briefing, suggest_filters,                # opportunity_briefing
    elaborate_items, generate_pdf,                     # report_generator
    generate_insights_pdf, generate_saved_jobs_pdf,    # report_pipeline
)
```
Consumers: radar bp (`generate_briefing`, `suggest_filters`), analytics bp
(`elaborate_items` + `generate_pdf`), saved bp (`generate_insights_pdf`).

## Structured-Outputs status (2.3 #4)
The three LLM calls were converted to `responses.parse(text_format=<schema>)` → validated
`output_parsed`, via `shared.llm.get_client`. Each module's own client / `json.loads` /
`re`-fence-stripping is gone, and the "respond with ONLY JSON" boilerplate is dropped from
every prompt. Prompts + schemas live in `config.py`.

| Call | Schema | Model |
|---|---|---|
| `opportunity_briefing.generate_briefing` | `BriefingResult` (`Literal` signal) | `CLASSIFIER_MODEL` |
| `opportunity_briefing.suggest_filters` | `FilterSuggestion` (nullable `min_salary`) | `CLASSIFIER_MODEL` |
| `report_generator.elaborate_items` | `ElaborationList` (was `chat.completions` + JSON array) | `CHAT_MODEL` |

Post-parse logic kept: `suggest_filters` still re-validates the returned occ_groups/states/
portals against the provided option lists; both briefing calls and the elaboration fall back
to a static structure on missing key / model failure. `report_pipeline.py` has **no LLM
call** (verified) — pure reportlab, nothing to convert. It still reads `at_geo` from
`services/at_geo` (its own package lands in 2.3 #8).

## Tests
`tests/jobs_intelligence_ai/services/reporting/unit_tests/` (12, offline):
`test_1_opportunity_briefing` (briefing + filter validation + fallbacks),
`test_2_report_generator` (elaboration merge-by-index + fallbacks + PDF emits `%PDF`),
`test_3_report_pipeline` (both PDF builders emit `%PDF`, fed a real `build_insights` payload).
`smoke_tests/test_reporting_smoke` (3, live-asserting): briefing sections, filter subset,
per-insight elaboration.
