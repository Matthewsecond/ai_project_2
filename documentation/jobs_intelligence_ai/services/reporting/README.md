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
├── report_pipeline.py       # Candidate Pipeline / Match Insights PDFs (pure reportlab)
├── session_chat.py          # grounded advisor chats for the Analytics + Radar tabs (prose)
└── company_summary.py       # AI summary of a company's hiring profile (Company tab; prose)
```

## Public API
```python
from jobs_intelligence_ai.services.reporting import (
    generate_briefing, suggest_filters,                # opportunity_briefing
    elaborate_items, generate_pdf,                     # report_generator
    generate_insights_pdf, generate_saved_jobs_pdf,    # report_pipeline
    analytics_chat, radar_chat,                         # session_chat
    summarize_company,                                 # company_summary
)
```
Consumers: radar bp (`generate_briefing`, `suggest_filters`, `radar_chat`), analytics bp
(`elaborate_items` + `generate_pdf`, `analytics_chat`), company bp (`summarize_company`),
saved bp (`generate_insights_pdf`).

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
| `session_chat.analytics_chat` / `radar_chat` | `AdvisorReply` (single prose `answer`) | `ADVISOR_MODEL` (= `CHAT_MODEL`) |
| `company_summary.summarize_company` | `CompanySummary` (single prose `summary`) | `COMPANY_SUMMARY_MODEL` (= `CLASSIFIER_MODEL`) |

Post-parse logic kept: `suggest_filters` still re-validates the returned occ_groups/states/
portals against the provided option lists; both briefing calls and the elaboration fall back
to a static structure on missing key / model failure. `report_pipeline.py` has **no LLM
call** (verified) — pure reportlab, nothing to convert. It still reads `at_geo` from
`services/at_geo` (its own package lands in 2.3 #8).

### session_chat (2.4)
The Analytics-tab assistant and Radar-tab advisor were relocated here from the
`analytics`/`radar` blueprints and converted off the legacy `chat.completions` + raw
`OpenAI()` client. They return **prose**, so `AdvisorReply` is a single `answer: str` field —
still the modern `responses.parse` path, no hand-parsing. Multi-turn history is passed in each
turn (no server-side session) and forwarded to the Responses API as a list of `input` messages;
the grounding context (saved items / market snapshot) is built into `instructions`. Either
raises on no-key / model error (the blueprint maps that to a 500).

### company_summary (2.4)
The Company-tab hiring-profile summary, relocated from the `company` blueprint and converted
off the legacy `chat.completions` + raw `OpenAI()` client. Prose, so `CompanySummary` is a
single `summary: str` field. Unlike the session chats it **returns "" on no-key / null /
error** (never raises) — the summary is an optional flourish on the company response, which
still renders without it.

## Tests
`tests/jobs_intelligence_ai/services/reporting/unit_tests/` (21, offline):
`test_1_opportunity_briefing` (briefing + filter validation + fallbacks),
`test_2_report_generator` (elaboration merge-by-index + fallbacks + PDF emits `%PDF`),
`test_3_report_pipeline` (both PDF builders emit `%PDF`, fed a real `build_insights` payload),
`test_4_session_chat` (both chats return the reply; items/snapshot grounded into instructions,
history+message forwarded as input; no-key/null/error raise),
`test_5_company_summary` (summary returned + trimmed; no-key/null/error → ""). 
`smoke_tests/test_reporting_smoke` (6, live-asserting): briefing sections, filter subset,
per-insight elaboration, analytics chat, radar chat, company summary.
