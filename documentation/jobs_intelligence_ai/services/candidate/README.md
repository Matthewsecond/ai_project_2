# services/candidate/

Everything about the candidate the recruiter is working with — persistence, sample CVs,
LinkedIn enrichment, and the candidate-assistant chat. Packaged in rework Stage 2.3 #7 from
`candidate_store.py` + `example_cv.py` + `profile_enricher.py`, plus the candidate assistant
relocated here from the old `chat.py` (whose **last** surface this was — `chat.py` is now
deleted).

## Layout
```
services/candidate/
├── __init__.py          # public API
├── config.py            # enricher + assistant prompts and Structured-Outputs schemas
├── store.py             # MySQL persistence for the saved-candidate pipeline (DB; no LLM)
├── example_cv.py        # sample candidate CV PDFs for the demo (pure reportlab)
├── profile_enricher.py  # AI-normalize a raw LinkedIn scrape (Structured Outputs)
└── assistant.py         # candidate-assistant chat: discuss + edit one candidate (Structured Outputs)
```

## Public API
```python
from jobs_intelligence_ai.services.candidate import store           # DB layer (submodule)
from jobs_intelligence_ai.services.candidate import (
    enrich_linkedin_profile, send_candidate_message, clear_candidate_session,
    generate_example_cv_pdf, generate_example_cv_pdf_2, generate_example_cv_pdf_sk,
)
```
Consumers: candidate bp (example CVs, enricher, assistant via `core`), saved/guided/cluster
bps (`store`).

## Structured-Outputs status (2.3 #7)
- ✅ **profile_enricher.enrich_linkedin_profile** → `responses.parse(text_format=LinkedInProfile)`
  (18-field schema, `Literal` seniority, nullable ints) via `shared.llm.get_client`; the
  own-`OpenAI()` client + `_parse_json` are deleted, "ONLY JSON" boilerplate dropped. The
  merge-over-base + provenance + base fallback (no key / error) are kept.
- ✅ **assistant.send_candidate_message** → `responses.parse(text_format=CandidateReply)`;
  `_parse_candidate` (trailing-JSON-block parser) is deleted. `profile_updates` is now an
  **explicit-field `ProfileUpdates` schema** (Optional per field; null = unchanged), and a
  nullable nested object marks pure-discussion turns. The shaping (drop null update fields,
  scalars-replace / arrays-append semantics) is preserved for the front-end.
- **store** — DB only (its `json.loads` deserializes a JSON column); switched no model code.
- **example_cv** — pure reportlab; no model call.

## Tests
`tests/jobs_intelligence_ai/services/candidate/unit_tests/` (12, offline): `test_1_profile_enricher`
(SO merge-over-base, empty-field guard, no-key/error → base), `test_2_assistant`
(reply→text, only-changed updates, pure-discussion → no edits, session continuity, fallbacks),
`test_3_example_cv` (all three PDF builders emit `%PDF`). `smoke_tests/test_candidate_smoke`
(3, live-asserting): enrichment, assistant discussion (no edits), assistant CV edit.
