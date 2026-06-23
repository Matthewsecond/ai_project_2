"""
stats — statistical helpers: salary benchmarks, market/opportunity snapshots, and
pure-Python job quality signals.

Public API (import from the package, not the submodules):

    from jobs_intelligence_ai.services.stats import get_group_stats, build_quality_context

- quality_score : pure signals from a job dict (no DB) — completeness, salary band,
  employment, freshness, description complexity, and the bundled build_quality_context.
- salary_stats  : salary benchmarks for an occupational group (DB-backed, cached).
- opportunity   : market snapshots (sector/state/portal/volume) + stale/urgent job lists (DB-backed).
"""
from .quality_score import (
    completeness_score,
    salary_signal,
    employment_signals,
    freshness_signal,
    description_complexity,
    build_quality_context,
)
from .salary_stats import get_group_stats, salary_percentile_rank, invalidate_cache
from .opportunity import (
    get_sector_snapshot,
    get_state_snapshot,
    get_portal_snapshot,
    get_volume_trend,
    get_summary_totals,
    get_stale_jobs,
    get_urgent_jobs,
)

__all__ = [
    # quality_score (pure)
    "completeness_score", "salary_signal", "employment_signals", "freshness_signal",
    "description_complexity", "build_quality_context",
    # salary_stats (DB)
    "get_group_stats", "salary_percentile_rank", "invalidate_cache",
    # opportunity (DB)
    "get_sector_snapshot", "get_state_snapshot", "get_portal_snapshot",
    "get_volume_trend", "get_summary_totals", "get_stale_jobs", "get_urgent_jobs",
]
