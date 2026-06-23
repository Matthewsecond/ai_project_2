"""
config.py — settings for the `enrichment` service (flat constants, per rework §5).

The home for this module's knobs. Each sub-feature's prompt + Structured-Outputs Pydantic
schema migrates here as it's converted (rescorer, highlighter in 2.3 #2b/#2c). Today the
per-feature dataclasses (RescorerConfig, HighlighterConfig) still live in their own files.
"""
from jobs_intelligence_ai import config

# Default models for the enrichment calls (sourced from global; override per feature).
MODEL            = config.CHAT_MODEL        # reasoning calls (rescore, highlight, quality)
CLASSIFIER_MODEL = config.CLASSIFIER_MODEL  # cheap batch classification (seniority)
