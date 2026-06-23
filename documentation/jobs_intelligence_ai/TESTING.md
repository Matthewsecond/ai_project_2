# Testing

How the test suite is organized, how to run it, and what currently exists.
The strategy was set as part of the modular rework — see [planning/RESTRUCTURE_PLAN.md](planning/RESTRUCTURE_PLAN.md) §10.

## Principle: the test tree mirrors the package

`tests/` mirrors `src/jobs_intelligence_ai/` — **one test package per module** — the
same convention used in the `Work` project. Each module/tier folder is a real package
(`__init__.py` + `__main__.py`), so any slice is runnable in isolation. This mirrors the
public-API principle: a service you can exercise on its own is a service with a clean boundary.

```
tests/
├── conftest.py          shared fixtures: col, sample_job_row, fake_engine
├── _runner.py           dispatch for `python -m tests.<...>`
├── _fake_db.py          fake sync SQLAlchemy engine/conn/result/row (DB-free unit tests)
├── _fixtures/samples.py deterministic sample data (CV, job row values, LLM responses)
└── jobs_intelligence_ai/
    ├── shared/unit_tests/              foundation: json, job, grading, taxonomy
    ├── services/<svc>/unit_tests/      one test package per service
    └── frontend/integration_tests/     Flask test_client route tests
```

## Tiers

| Tier | What | Mocks |
|---|---|---|
| `unit_tests/` | pure logic, the bulk of coverage | `shared/` none; services mock `shared/llm.get_client` + use `_fake_db` |
| `integration_tests/` | wired components (e.g. `frontend` routes) | Flask `test_client`, services mocked |
| `smoke_tests/` | live OpenAI + MySQL, `@pytest.mark.smoke`, excluded by default | none (real) |

**Two seams make services testable offline** (a bonus reason for the `shared/` layer):
mocking the single OpenAI client at `shared/llm.get_client()` covers every LLM path, and
`_fake_db.FakeEngine` (monkeypatching `infra.database.get_engine`) covers DB paths.

## Running

```bash
pytest -m "not smoke"          # default gate — everything except live smoke tests
pytest -m smoke                # live smoke (needs OPENAI_API_KEY + MySQL)
pytest tests/jobs_intelligence_ai/shared          # one module

python -m tests                                    # whole tree as packages
python -m tests.jobs_intelligence_ai.shared unit   # one tier
```

The live tests self-skip without an OpenAI key + vector store, so the offline unit tests
always run anywhere.

## Current inventory

**Foundation — `shared/unit_tests/` (26 tests, offline)** — pin the current behavior of the
helpers being merged into `shared/` in rework Stage 2.1; the equivalence guard for that merge:
- `test_1_json` — `parse_json`, `chat._parse`, `chat._parse_candidate` (fenced/bare/embedded JSON, citation-marker stripping)
- `test_2_job` — `serialize_job` (field mapping, defaults, blank handling, stable shape)
- `test_3_grading` — `grade()` A/B/C bands incl. boundaries
- `test_4_taxonomy` — sector/role taxonomy lookups
- `test_5_llm` — `shared/llm.get_client` singleton contract + mock seam (added 2.1a)

**Search — `services/search/`**:
- `unit_tests/test_grader` (5, **offline**) — the Structured-Outputs grader: mocks
  `client.responses.parse`, asserts scores are applied/clamped/banded and that a model
  failure or short reply falls back to neutral. The template for service conversions.
- `unit_tests/test_search_stability` (2, **live**) — retrieval-set determinism (Stage 1)
  and A+B result overlap end-to-end (Stage 2), via mean pairwise Jaccard.
- `smoke_tests/test_grader_smoke` (1, **live, asserts**) — hits the real API; asserts the
  structured grader returns one valid in-range score per job and that a clear-cut candidate
  outscores an obvious mismatch. Catches "structured call is misconfigured/rejected".
- `smoke_tests/test_search_smoke` (1, **live**) — runs the real Orchestrator and prints matches; no asserts (eyeball).

**Services — `services/stats/unit_tests/` (14, offline)** — the first repackaged service (2.3 #1):
`test_1_quality_score` (pure quality signals) + `test_2_opportunity` (SQL filter-clause builder + type converter). DB query functions covered by boot + the radar tab.

**Services — `services/enrichment/` (2.3 #2)** — offline `unit_tests/` (26): rescorer(6), highlighter(6), seniority(6), quality(5), match_insights(3) — mock `responses.parse` (apply + clamp/skip + fallback); match_insights is pure (no LLM). Live `smoke_tests/` (4, asserts): rescorer, highlighter, seniority, quality.

**Services — `services/interview/` (2.3 #3)** — offline `unit_tests/test_1_interview` (18): inject a fake client, assert the post-processing rules Structured Outputs can't express — score clamping, the `final` override that forces a score, follow-up exhaustion on an empty question, status/impact normalisation — plus the input guards and the no-key / API-failure / `output_parsed is None` fallbacks. Live `smoke_tests/test_interview_smoke` (2, asserts): generate gap-based questions, and score a strong answer (complete + in-range).

**Default gate:** `pytest -m "not smoke"` → **91 passed, 8 deselected** — offline foundation + stats + enrichment + interview + grader unit tests, plus the live search stability tests (the live-asserting smoke tests deselected).

## Testing Structured-Outputs calls (the conversion pattern)

Model calls now use `client.responses.parse(text_format=PydanticModel)` → `output_parsed`.
That's a single, clean boundary to mock — so each converted call site gets **offline**
unit tests with no network:

```python
class _FakeResponses:
    def __init__(self, parsed=None, exc=None): self._parsed, self._exc = parsed, exc
    def parse(self, **kw):
        if self._exc: raise self._exc
        return type("Resp", (), {"output_parsed": self._parsed})()
class _FakeClient:
    def __init__(self, parsed=None, exc=None): self.responses = _FakeResponses(parsed, exc)
```

Assert two things every time: (1) the **happy path** applies `output_parsed` correctly,
and (2) the **failure path** (exception or `output_parsed is None`, i.e. a refusal) falls
back gracefully. See `services/search/unit_tests/test_grader.py` for the template.

**But mocks can't prove the call itself works** — that the API accepts the schema, that
`file_search` + structured outputs coexist, that results are sensible. So every conversion
*also* gets a **live smoke test that ASSERTS** (marked `@pytest.mark.smoke`): call the real
API and check `output_parsed` is non-None with the expected shape and in-range/sane values.
See `services/search/smoke_tests/test_grader_smoke.py` for the template.

**Rule — two layers per conversion, both in the same step (definition of done):**
1. **offline unit** (mock the boundary) — logic + fallback, always runs.
2. **live smoke that asserts** (`@pytest.mark.smoke`) — proves the real structured call works.

**Every test function carries a one-line docstring** stating what it verifies, in plain
language — the test list should read like a spec without decoding the assertions. Mock
helpers get a one-line docstring too. See `test_grader.py` for the house style.

## Gaps (filled as the rework proceeds)

Per-service `unit_tests/` (reporting, chat, clustering, candidate, geo, auth) and
`frontend/integration_tests/` are scaffolded but empty — each is written when its module is
repackaged in rework Stage 2.3 / 2.4. Done so far: stats, enrichment, interview.
