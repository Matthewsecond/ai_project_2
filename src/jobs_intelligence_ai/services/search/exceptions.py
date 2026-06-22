"""
exceptions.py — The search module's exception hierarchy.

Every failure mode raises a typed SearchError subclass, so a caller (or a log
line) can tell immediately which worker failed — the vector-store pass, the DB
resolution, or configuration — instead of staring at a bare RuntimeError.

    SearchError
      ├─ ConfigError           — can't run as configured (missing key / store)
      ├─ EmbeddingSearchError  — a vector-store pass failed
      └─ JobSearchError        — resolving ids to DB rows failed
"""


class SearchError(Exception):
    """Base class for every error raised inside the search module."""


class ConfigError(SearchError):
    """The search can't run as configured (e.g. missing OpenAI key / vector store)."""


class EmbeddingSearchError(SearchError):
    """A vector-store pass (EmbeddingSearch) failed."""


class JobSearchError(SearchError):
    """Resolving matched ids to DB rows (JobSearch) failed."""
