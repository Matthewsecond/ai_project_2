"""Pytest configuration + shared fixtures.

The package is installed editable (`pip install -e .`), so tests import it directly:
`from jobs_intelligence_ai.search.orchestrator import Orchestrator`.

Fixtures here are shared across the whole tree. Tier-specific helpers live in
tests/_fake_db.py (fake SQLAlchemy connection) and tests/_fixtures/ (sample data).
"""
import pytest

from tests._fixtures import samples


@pytest.fixture
def col():
    """The active country's logical→DB column mapping (config.COL)."""
    from jobs_intelligence_ai import config
    return config.COL


@pytest.fixture
def sample_job_row(col):
    """A raw DB job row (real DB column names) built from SAMPLE_JOB_VALUES.

    Mapped through the active COL so it stays correct for whichever country
    profile is active during the test run.
    """
    return {col[k]: v for k, v in samples.SAMPLE_JOB_VALUES.items() if k in col}


@pytest.fixture
def fake_engine():
    """Factory for a FakeEngine — pass it a {sql_substring: rows} responses dict."""
    from tests._fake_db import FakeEngine
    return FakeEngine
