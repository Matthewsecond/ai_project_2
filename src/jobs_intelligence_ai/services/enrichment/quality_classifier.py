"""
helpers/quality_classifier.py — AI-powered job quality assessment.

The model is given:
  • The full job description / responsibilities / skills
  • Structured signals pre-computed by statistics/quality_score.py
    (salary vs group mean, completeness, employment terms, freshness)
  • Group salary statistics as market context

Its primary task: reason about whether the RESPONSIBILITIES and required
SKILLS are fairly compensated.  A posting that demands senior architect
duties at €2,400/month should score low regardless of the group mean,
because the ask/offer ratio is imbalanced.

Output per job:
  quality       "high" | "mid" | "low"
  score         0.0–1.0
  verdict       one sentence — the key quality signal
  fit           "overpaying" | "fair" | "underpaying" | "unknown"
  flags         list of short observations (max 4)
"""
import logging

from jobs_intelligence_ai import config
from jobs_intelligence_ai.shared.llm import get_client
from .config import QUALITY_PROMPT, QualityResults

logger = logging.getLogger(__name__)


def classify_quality(jobs: list[dict], group_stats: dict) -> list[dict]:
    """
    Assess quality for a batch of jobs in one AI call.

    Parameters
    ----------
    jobs        : list of job dicts (must have at minimum title + description)
    group_stats : output of statistics.salary_stats.get_group_stats()

    Returns
    -------
    Same list, each job enriched with:
        quality, quality_score, quality_verdict, quality_fit, quality_flags
    """
    if not jobs:
        return jobs

    if not config.OPENAI_API_KEY:
        return _fallback(jobs)

    from jobs_intelligence_ai.services.stats import build_quality_context

    # Build the prompt body — one block per job
    market_context = _format_market_context(group_stats)
    job_blocks = []
    for i, j in enumerate(jobs):
        ctx = build_quality_context(j, group_stats)
        block = _format_job_block(i, j, ctx)
        job_blocks.append(block)

    user_input = (
        f"Market context for occupational group '{group_stats.get('occ_group', 'unknown')}':\n"
        f"{market_context}\n\n"
        f"Assess the following {len(jobs)} job posting(s):\n\n"
        + "\n\n---\n\n".join(job_blocks)
    )

    try:
        response = get_client().responses.parse(
            model=config.CLASSIFIER_MODEL,
            instructions=QUALITY_PROMPT,
            input=user_input,
            text_format=QualityResults,
        )
        results = response.output_parsed.items if response.output_parsed else []

        for item in results:
            if not (0 <= item.i < len(jobs)):
                continue
            j = jobs[item.i]
            j["quality"]         = item.quality
            j["quality_score"]   = float(item.score)
            j["quality_verdict"] = item.verdict
            j["quality_fit"]     = item.fit
            j["quality_flags"]   = item.flags

        # Fill any the model skipped
        for j in jobs:
            if "quality" not in j:
                _apply_fallback_single(j)

    except Exception as exc:
        logger.warning("AI quality classification failed (%s) — using fallback", exc)
        return _fallback(jobs)

    return jobs


# ── Prompt helpers ────────────────────────────────────────────────────────────

def _format_market_context(stats: dict) -> str:
    if not stats.get("count"):
        return "No salary statistics available for this group."
    return (
        f"  Group: {stats['occ_group']}  |  n={stats['count']} jobs with salary data\n"
        f"  Mean: €{stats['mean']:,.0f}  |  Median: €{stats['median']:,.0f}  "
        f"|  P25: €{stats['p25']:,.0f}  |  P75: €{stats['p75']:,.0f}"
    )


def _format_job_block(i: int, job: dict, ctx: dict) -> str:
    sal_sig = ctx["salary_signal"]
    emp     = ctx["employment"]
    fresh   = ctx["freshness"]
    desc_s  = ctx["description_signals"]

    salary_line = "Not specified"
    if sal_sig["job_salary"]:
        salary_line = f"€{sal_sig['job_salary']:,.0f}/month"
        if sal_sig["vs_mean_pct"] is not None:
            direction = "above" if sal_sig["vs_mean_pct"] >= 0 else "below"
            salary_line += f"  ({abs(sal_sig['vs_mean_pct']):.0f}% {direction} group mean, band: {sal_sig['band']})"

    desc = str(job.get("description") or job.get("description_snippet") or job.get("summary") or "")
    skills = job.get("skills_en") or job.get("skills") or ""

    lines = [
        f"[{i}] {job.get('title', '—')}  |  {job.get('company', '—')}",
        f"Salary: {salary_line}",
        f"Employment: {job.get('employment_relationship') or '—'}  |  Work time: {job.get('work_time') or '—'}",
        f"Education required: {job.get('education') or '—'}",
        f"Skills: {str(skills)[:300] or '—'}",
        f"Completeness score: {ctx['completeness']:.0%}",
        f"Posting freshness: {fresh['days_old']} days old" + (" [DEADLINE PASSED]" if fresh["deadline_passed"] else ""),
        f"Description signals: {desc_s['word_count']} words, ~{desc_s['tech_term_count']} tech terms"
        + (", leadership role" if desc_s["has_leadership"] else "")
        + (f", requires {desc_s['required_years']}+ years" if desc_s["required_years"] else ""),
        "",
        "Description (excerpt):",
        desc[:600] + ("…" if len(desc) > 600 else ""),
    ]
    return "\n".join(lines)


# ── Fallback (no API key or error) ────────────────────────────────────────────

def _apply_fallback_single(job: dict) -> None:
    """Simple rule-based quality estimate when AI is unavailable."""
    from jobs_intelligence_ai.services.stats import completeness_score, salary_signal

    comp = completeness_score(job)
    sal_s = salary_signal(job, {})  # no group stats
    score = comp * 0.6 + 0.4  # completeness-only base

    if comp >= 0.8:
        quality = "high"
    elif comp >= 0.5:
        quality = "mid"
    else:
        quality = "low"

    job.setdefault("quality",         quality)
    job.setdefault("quality_score",   round(score, 2))
    job.setdefault("quality_verdict", "Quality estimated from posting completeness (AI unavailable).")
    job.setdefault("quality_fit",     "unknown")
    job.setdefault("quality_flags",   [])


def _fallback(jobs: list[dict]) -> list[dict]:
    for j in jobs:
        _apply_fallback_single(j)
    return jobs
