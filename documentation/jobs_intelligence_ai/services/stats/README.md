# services/stats/

Statistical helpers — the first service packaged in rework Stage 2.3. No LLM calls.

## Layout
```
services/stats/
├── __init__.py       # public API (import from here, not the submodules)
├── config.py         # COMPLETENESS_FIELDS weights, FRESHNESS_WINDOW/DEFAULT days
├── __main__.py       # python -m …services.stats → prints quality signals for a sample job (offline)
├── quality_score.py  # PURE signals from a job dict (no DB)
├── salary_stats.py   # salary benchmarks per occupational group (DB, cached)
└── opportunity.py    # market snapshots + stale/urgent job lists (DB)
```

## Public API
```python
from jobs_intelligence_ai.services.stats import (
    build_quality_context, completeness_score, salary_signal,   # pure quality signals
    get_group_stats, salary_percentile_rank,                    # salary benchmarks (DB)
    get_sector_snapshot, get_summary_totals, get_stale_jobs,    # opportunity snapshots (DB)
)
```
Consumers: the `search`, `radar`, and (quality classifier in) `enrichment` paths.

## Tests
`tests/jobs_intelligence_ai/services/stats/unit_tests/` (14, offline):
- `test_1_quality_score` — completeness, salary bands, employment flags, freshness, description signals, the bundle.
- `test_2_opportunity` — the pure SQL filter-clause builder + the MySQL→native type converter.

The DB-backed query functions are unchanged by the move (pure relocation) and covered by app boot + the radar tab. See also [SALARY_ANALYSIS.md](SALARY_ANALYSIS.md).

> Two pre-existing quality-signal bugs were found while writing tests (the `unbefristet`
> substring trips `is_temp`; `days_old or 30` mis-scores a posted-today job). Flagged for a
> separate fix; the tests currently pin the clean cases with NOTEs.
