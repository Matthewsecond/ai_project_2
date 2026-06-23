"""
config.py — settings for the `stats` service (flat constants, per rework §5).

The single home for this module's knobs. The opportunity SQL staleness thresholds
(30/60 days, 14-day urgent window) are still inline in opportunity.py — they're baked
into the GROUP BY queries; externalize later if they need tuning.
"""

# ── Completeness scoring: (job field, weight) — how much each present field counts ──
COMPLETENESS_FIELDS = [
    ("description", 3),   # longest description = most weight
    ("skills_en",   2),
    ("salary",      2),
    ("url",         1),
    ("contacts",    1),
    ("city",        1),
]

# ── Freshness normalization ──────────────────────────────────────────────────────
FRESHNESS_WINDOW_DAYS  = 90   # a job this old scores ~0; newer scores toward 1.0
FRESHNESS_DEFAULT_DAYS = 30   # assumed age when the posted date is missing
