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
- ⏳ **highlighter** → Structured Outputs (2.3 #2c): same pattern (indices schema).
- `seniority_classifier`, `quality_classifier` — model calls to review/convert when reached.
- `match_insights` — verify (may be pure assembly over stats, no LLM).

## Tests
`tests/jobs_intelligence_ai/services/enrichment/unit_tests/` — added with each conversion
(offline mock of `responses.parse` + live-asserting smoke), per the testing standard.
