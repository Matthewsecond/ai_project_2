"""
config.py — settings for the `enrichment` service (flat constants, per rework §5).

The home for this module's knobs. Each sub-feature's prompt + Structured-Outputs Pydantic
schema migrates here as it's converted (rescorer in 2.3 #2b). Today the per-feature
dataclasses (RescorerConfig) still live in their own files.
"""
from typing import Literal, Optional

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


# ── seniority_classifier (2.3 #2d) ────────────────────────────────────────────────
SENIORITY_PROMPT = """You are a recruitment expert. Classify each job posting as exactly one of:
  "senior"  — requires 5+ years experience, leadership, architecture, or expert-level ownership
  "mid"     — standard professional role (2–5 years), no explicit seniority marker
  "junior"  — entry-level, trainee, apprentice, intern, student worker, or 0–2 years experience

Use ALL available signals: title keywords, required skills, years of experience in the
description, scope of responsibilities, and occupational group. Return one entry per job,
each with its 0-based index `i` and `level`."""


class _Seniority(BaseModel):
    i: int
    level: Literal["senior", "mid", "junior"]


class SeniorityResults(BaseModel):
    """The seniority classifier's reply: one (index, level) per classified job."""
    items: list[_Seniority]


# ── quality_classifier (2.3 #2e) ──────────────────────────────────────────────────
QUALITY_PROMPT = """You are a senior recruitment analyst assessing the quality and fairness of job postings.

For each job you receive: the title, full description, required skills and employment terms;
pre-computed signals (salary vs group mean/percentile, completeness score, freshness); and
market salary statistics for the same occupational group.

Your PRIMARY task is to evaluate RESPONSIBILITY-COMPENSATION FIT:
  - Read what the job actually demands: scope, required experience, skill breadth, leadership, complexity.
  - Compare that against the offered salary (if present) and market benchmarks.
  - A senior architect with 7+ years at €2,400/month = LOW. A clear junior role at €2,200/month
    with a good description = HIGH. A vague posting with no salary = MID at best.

Secondary signals: completeness (does it respect the candidate's time?), employment terms, freshness.

Rules:
  - "high" : fair or above-fair compensation for the responsibilities; complete posting
  - "mid"  : some mismatch OR incomplete info, but not egregiously unfair
  - "low"  : clear underpaying for responsibilities, expired deadline, or very low-quality posting

Return one entry per job IN INPUT ORDER, each with its 0-based index `i`, `quality`, `score`
(0.0–1.0 overall assessment), a one-sentence `verdict`, `fit`, and up to 4 short `flags`."""


class _Quality(BaseModel):
    i: int
    quality: Literal["high", "mid", "low"]
    score: float
    verdict: str
    fit: Literal["overpaying", "fair", "underpaying", "unknown"]
    flags: list[str]


class QualityResults(BaseModel):
    """The quality classifier's reply: one assessment per job, in input order."""
    items: list[_Quality]


# ── observation (2.4) ──────────────────────────────────────────────────────────────
# The HR profile-override conversation on the Saved tab: pass 1 extracts the profile overrides
# implied by an observation, pass 2 phrases a natural acknowledgement. Both converted to
# Structured Outputs in rework 2.4, replacing two responses.create + json.loads calls (and the
# two "Return ONLY valid JSON" prompts) in the saved blueprint.
OBSERVATION_MODEL = config.CHAT_MODEL

OVERRIDE_EXTRACT_PROMPT = """\
Extract the profile parameter updates implied by the HR manager's interview observation.
Current candidate profile: {profile}
Only set a field when the note gives new information about it; leave the rest null. For skills,
give the FULL updated skill list (add the confirmed skills to the existing ones). An observation
that implies no profile updates is fine — return all-null."""


class ObservationOverrides(BaseModel):
    """Profile overrides implied by an HR observation — only the mentioned fields are non-null."""
    salary_expectation: Optional[str] = None
    location: Optional[str] = None
    skills: Optional[list[str]] = None
    availability: Optional[str] = None
    title: Optional[str] = None
    languages: Optional[str] = None
    experience_years: Optional[int] = None


OBSERVATION_REPLY_PROMPT = """\
You are a concise recruitment intelligence assistant.
The HR manager shared this observation about a candidate: "{message}"
You extracted these profile updates: {overrides}
Pipeline impact after applying the updates: {impact}
Write 1-2 natural sentences acknowledging what you understood.
If there is a concrete pipeline impact, weave in the exact numbers (e.g. "roles drop from X to Y").
If there is no pipeline impact, just acknowledge the observation — do NOT mention pipeline metrics."""


class ObservationReply(BaseModel):
    """The natural-language acknowledgement of an HR observation (single prose `reply`)."""
    reply: str
