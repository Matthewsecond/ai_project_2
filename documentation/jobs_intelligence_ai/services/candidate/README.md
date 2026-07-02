# services/candidate/

Everything about the candidate the recruiter is working with — persistence, sample CVs, and
LinkedIn enrichment. Packaged in rework Stage 2.3 #7 from `candidate_store.py` + `example_cv.py`
+ `profile_enricher.py`.

> The docked "candidate assistant" chat (discuss + edit one candidate) was removed from
> `master` on 2026-07-02 and lives on `develop` only — see the Frontend + DB rework plan's
> decisions log. `assistant.py` no longer exists on `master`.

## Layout
```
services/candidate/
├── __init__.py          # public API
├── config.py            # enricher + guided prompts and Structured-Outputs schemas
├── store.py             # MySQL persistence for the saved-candidate pipeline (DB; no LLM)
├── example_cv.py        # sample candidate CV PDFs for the demo (pure reportlab)
├── profile_enricher.py  # AI-normalize a raw LinkedIn scrape (Structured Outputs)
├── profile_parser.py    # parse a structured profile from raw CV text (Structured Outputs)
└── guided_builder.py    # guided "target candidate" builder chat (Structured Outputs)
```

## Public API
```python
from jobs_intelligence_ai.services.candidate import store           # DB layer (submodule)
from jobs_intelligence_ai.services.candidate import (
    enrich_linkedin_profile, parse_candidate_profile,
    extract_guided_fields, phrase_guided_reply,
    generate_example_cv_pdf, generate_example_cv_pdf_2, generate_example_cv_pdf_sk,
)
```
Consumers: candidate bp (example CVs, enricher, profile parser), guided bp (guided_builder),
saved/guided/cluster bps (`store`).

## Structured-Outputs status (2.3 #7)
- ✅ **profile_enricher.enrich_linkedin_profile** → `responses.parse(text_format=LinkedInProfile)`
  (18-field schema, `Literal` seniority, nullable ints) via `shared.llm.get_client`; the
  own-`OpenAI()` client + `_parse_json` are deleted, "ONLY JSON" boilerplate dropped. The
  merge-over-base + provenance + base fallback (no key / error) are kept.
- ✅ **profile_parser.parse_candidate_profile** → `responses.parse(text_format=CandidateProfile)`
  (added in 2.4): relocated the candidate blueprint's inline `chat.completions` CV-text parser
  here. The own-`OpenAI()` client + the "ONLY JSON" prompt + the regex-strip/`json.loads`
  fallback are gone; the blueprint now just calls the service and `jsonify`s the dict.
- ✅ **guided_builder.extract_guided_fields / phrase_guided_reply** → two `responses.parse`
  calls (added in 2.4): the guided builder's two-pass turn relocated from the guided blueprint.
  `extract_guided_fields` (`GuidedFieldUpdates`; only the mentioned fields survive) and
  `phrase_guided_reply` (`GuidedReply` — reply + the next narrowing question, `options`/
  `suggestions` chips) replace the shared `_gpt_json` helper (a `responses.create` + `json.loads`
  round-trip behind two "Return ONLY valid JSON" prompts) the guided bp used to borrow from the
  saved blueprint. extract returns `{}` on no key and **raises** on a model error (bp → 500);
  reply degrades to `{}` (bp applies safe defaults) so the chat keeps working. The blueprint
  keeps all the grounding (live DB faceting, taxonomy catalog, salary benchmark, chip-routing).
- **store** — DB only (its `json.loads` deserializes a JSON column); switched no model code.
- **example_cv** — pure reportlab; no model call.

## Tests
`tests/jobs_intelligence_ai/services/candidate/unit_tests/` (offline): `test_1_profile_enricher`
(SO merge-over-base, empty-field guard, no-key/error → base), `test_3_example_cv` (all three PDF
builders emit `%PDF`), `test_4_profile_parser` (SO parse→dict, no-key/null/error raise),
`test_5_guided_builder` (SO field extraction drops empty fields + grounds the catalog; reply→dict
with `{value,label}` options; extract {}/raises, reply always degrades to {}).
`smoke_tests/test_candidate_smoke` (live-asserting): enrichment, CV-text parse, guided field
extraction, guided reply phrasing.
