# Testing

How the test suite is organized, how to run it, and what currently exists.
The strategy was set as part of the modular rework — see [RESTRUCTURE_PLAN.md](RESTRUCTURE_PLAN.md) §10.

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

**Foundation — `shared/unit_tests/` (24 tests, offline)** — pin the current behavior of the
helpers being merged into `shared/` in rework Stage 2.1; the equivalence guard for that merge:
- `test_1_json` — `parse_json`, `chat._parse`, `chat._parse_candidate` (fenced/bare/embedded JSON, citation-marker stripping)
- `test_2_job` — `serialize_job` (field mapping, defaults, blank handling, stable shape)
- `test_3_grading` — `grade()` A/B/C bands incl. boundaries
- `test_4_taxonomy` — sector/role taxonomy lookups

**Search — `services/search/` (pre-existing, live)**:
- `unit_tests/test_search_stability` (2) — retrieval-set determinism (Stage 1) and A+B
  result overlap end-to-end (Stage 2), via mean pairwise Jaccard. Splits a retrieval
  regression from grader jitter.
- `smoke_tests/test_search_smoke` (1) — runs the real Orchestrator and prints matches; no asserts.

**Default gate:** `pytest -m "not smoke"` → **26 passed, 1 deselected**.

## Gaps (filled as the rework proceeds)

Per-service `unit_tests/` (stats, enrichment, interview, reporting, chat, clustering,
candidate, geo, auth) and `frontend/integration_tests/` are scaffolded but empty — each
is written when its module is repackaged in rework Stage 2.3 / 2.4.
