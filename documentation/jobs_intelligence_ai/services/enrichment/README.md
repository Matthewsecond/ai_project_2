# services/enrichment/

Post-retrieval operations that enrich / re-score a job result set the recruiter already
has. None of these are search (they never add or drop jobs). Packaged in rework Stage 2.3 #2.

## Layout
```
services/enrichment/
├── __init__.py            # public API
├── config.py              # enrichment model defaults; per-feature prompts/SO schemas migrate here
├── seniority_classifier.py # tag each job's seniority (batched model call)
├── quality_classifier.py   # AI quality assessment (uses stats.build_quality_context)
├── match_insights.py       # per-candidate "Match Insights" dashboard payload
├── rescorer.py             # re-grade a frozen job set vs an edited profile
└── highlighter.py          # flag jobs matching a natural-language criterion
```

## Public API
```python
from jobs_intelligence_ai.services.enrichment import (
    classify_seniority, classify_quality, build_insights, Rescorer, Highlighter,
)
```
Consumers: `search` orchestrator (seniority) + search bp (Rescorer/Highlighter/quality),
saved bp (match_insights), chat (seniority).

## Structured-Outputs status (2.3 #2)
- ✅ **rescorer** (2.3 #2b): `responses.parse(text_format=RescoreResults)` + `shared.get_client`; `parse_json` gone. Prompt + schema live in `config.py`. Tests: 6 offline + 1 live smoke.
- ✅ **highlighter** (2.3 #2c): `responses.parse(text_format=HighlightResult)` + `shared.get_client`; `parse_json` gone. Prompt + schema in `config.py`. Tests: 6 offline + 1 live smoke.
- ✅ **seniority_classifier** (2.3 #2d): `responses.parse(text_format=SeniorityResults)`, `Literal` levels, `shared.get_client`; keyword fallback kept. 6 offline + 1 live smoke.
- ✅ **quality_classifier** (2.3 #2e): `responses.parse(text_format=QualityResults)`, `Literal` quality/fit; rule-based fallback kept. 5 offline + 1 live smoke.
- ✅ **match_insights** — verified **no LLM** (pure assembly + optional DB market lookup); nothing to convert. 3 offline tests.

All hand-rolled JSON parsing in `enrichment/` is gone; every model call uses Structured Outputs.
Prompts + Pydantic schemas live in `config.py`.

## Tests
`tests/jobs_intelligence_ai/services/enrichment/unit_tests/` — added with each conversion
(offline mock of `responses.parse` + live-asserting smoke), per the testing standard.
