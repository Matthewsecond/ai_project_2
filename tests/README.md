# Tests

The test tree **mirrors `src/jobs_intelligence_ai/`** — one test package per module —
following the convention used across the `Work` project.

## Layout

```
tests/
├── conftest.py          shared fixtures (col, sample_job_row, fake_engine)
├── _runner.py           launcher helpers for `python -m tests.<...>`
├── _fake_db.py          fake sync SQLAlchemy engine/connection (unit tests, no live DB)
├── _fixtures/           deterministic sample data (samples.py)
└── jobs_intelligence_ai/
    ├── shared/unit_tests/              foundation: json, job, grading, taxonomy
    ├── services/<svc>/unit_tests/      one test package per service
    └── frontend/integration_tests/     Flask test_client route tests
```

## Tiers

- **`unit_tests/`** — pure logic. `shared/` needs no mocks; services mock the OpenAI
  client (`shared/llm.get_client`) and use `_fake_db` for the database. The bulk of coverage.
- **`integration_tests/`** — wired components (e.g. `frontend` routes via Flask `test_client`).
- **`smoke_tests/`** — live OpenAI + MySQL, marked `@pytest.mark.smoke`, **excluded by default**.

Files are numbered: `test_1_*.py`, `test_2_*.py`, …

## Running

```bash
pytest -m "not smoke"          # default: everything except live smoke tests
pytest -m smoke                # live smoke tests (need OpenAI key + MySQL)
pytest tests/jobs_intelligence_ai/shared        # one module's tests

# Or run a slice as a package (mirrors the public-API principle):
python -m tests                                  # whole tree
python -m tests.jobs_intelligence_ai.shared      # one module
python -m tests.jobs_intelligence_ai.services.search unit   # one tier
```

## Conventions for new tests

- A new service module gets its own `tests/.../services/<svc>/unit_tests/` package.
- Mock `shared/llm.get_client` to test LLM paths offline; use `_fake_db.FakeEngine`
  (monkeypatch `infra.database.get_engine`) to test DB paths offline.
- Keep sample inputs in `_fixtures/samples.py` so they're shared and deterministic.
