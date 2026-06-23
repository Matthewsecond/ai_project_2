"""
config.py — settings for the `enrichment` service (flat constants, per rework §5).

The home for this module's knobs. Each sub-feature's prompt + Structured-Outputs Pydantic
schema migrates here as it's converted (rescorer, highlighter in 2.3 #2b/#2c). Today the
per-feature dataclasses (RescorerConfig, HighlighterConfig) still live in their own files.
"""
from pydantic import BaseModel

from jobs_intelligence_ai import config

# Default models for the enrichment calls (sourced from global; override per feature).
MODEL            = config.CHAT_MODEL        # reasoning calls (rescore, highlight, quality)
CLASSIFIER_MODEL = config.CLASSIFIER_MODEL  # cheap batch classification (seniority)


# ── rescorer (2.3 #2b) ────────────────────────────────────────────────────────────
RESCORE_PROMPT = """You are a job-matching engine for Jobs Intelligence {label}.
You are given ONE candidate profile and a FIXED list of jobs. Score how well THIS \
candidate fits EACH job, one entry per job IN THE SAME ORDER — do not add or drop jobs.

For each job provide:
  score        — 0.0–1.0 fit confidence
  match_reason — one sentence, max 22 words

Use the full range: ~0.70+ for strong fits, ~0.50–0.70 for partial fits, below 0.50 \
for weak ones. Be sensitive to every detail in the profile, so scores shift when the \
profile changes (e.g. an added skill, certification, or years of experience)."""


class _ScoredJob(BaseModel):
    """One job's re-grade — Structured Outputs constrains the model to this shape."""
    score: float
    match_reason: str


class RescoreResults(BaseModel):
    """The rescorer's reply: one _ScoredJob per job, in the same order as the input."""
    scores: list[_ScoredJob]
