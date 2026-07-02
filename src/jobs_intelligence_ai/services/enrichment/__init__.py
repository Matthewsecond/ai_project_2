"""
enrichment — operations that enrich / re-score a job result set the recruiter already has.

Bundles the post-retrieval helpers (none of these are search — they never add or drop jobs):

- seniority_classifier : tag each job's seniority level (batched model call)
- quality_classifier   : AI quality assessment (uses stats.build_quality_context as input)
- match_insights       : build the per-candidate "Match Insights" dashboard payload
- rescorer             : re-grade a frozen job set against an edited candidate profile
- observation          : HR profile-override conversation (extract overrides + phrase reply)

Public API — import from the package:

    from jobs_intelligence_ai.services.enrichment import classify_seniority, Rescorer
"""
from .seniority_classifier import classify_seniority
from .quality_classifier import classify_quality
from .match_insights import build_insights
from .rescorer import Rescorer, RescorerConfig
from .observation import extract_profile_overrides, phrase_observation_reply

__all__ = [
    "classify_seniority",
    "classify_quality",
    "build_insights",
    "Rescorer", "RescorerConfig",
    "extract_profile_overrides", "phrase_observation_reply",
]
