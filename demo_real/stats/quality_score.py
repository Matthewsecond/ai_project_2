"""
statistics/quality_score.py — Pure-Python quality signal extraction.

These are fast, deterministic signals computed directly from job fields.
The AI quality classifier (helpers/quality_classifier.py) uses these as
structured inputs so it doesn't have to re-derive them from raw text.
"""
from __future__ import annotations
import re
from datetime import date, datetime


# ── Completeness ─────────────────────────────────────────────────────────────

_COMPLETENESS_FIELDS = [
    ("description", 3),   # longest description = most weight
    ("skills_en",   2),
    ("salary",      2),
    ("url",         1),
    ("contacts",    1),
    ("city",        1),
]


def completeness_score(job: dict) -> float:
    """0.0–1.0: how much of the important info is present."""
    total_weight = sum(w for _, w in _COMPLETENESS_FIELDS)
    earned = 0
    for field, weight in _COMPLETENESS_FIELDS:
        v = job.get(field)
        if v and str(v).strip():
            earned += weight
    return round(earned / total_weight, 3)


# ── Salary vs group stats ─────────────────────────────────────────────────────

def salary_signal(job: dict, group_stats: dict) -> dict:
    """
    Returns structured salary comparison data for the AI to reason about.
    {
        "job_salary":    float | None,
        "group_mean":    float | None,
        "group_median":  float | None,
        "group_p25":     float | None,
        "group_p75":     float | None,
        "group_count":   int,
        "vs_mean_pct":   float | None,   # +20 means 20% above mean
        "band":          str,             # "below_p25" | "p25_median" | "median_p75" | "above_p75" | "unknown"
    }
    """
    try:
        sal = float(job.get("salary") or 0)
    except (TypeError, ValueError):
        sal = 0.0

    if not group_stats.get("count") or sal <= 0:
        return {
            "job_salary": sal or None,
            "group_mean": group_stats.get("mean"),
            "group_median": group_stats.get("median"),
            "group_p25": group_stats.get("p25"),
            "group_p75": group_stats.get("p75"),
            "group_count": group_stats.get("count", 0),
            "vs_mean_pct": None,
            "band": "unknown",
        }

    mean   = group_stats["mean"]
    median = group_stats["median"]
    p25    = group_stats["p25"]
    p75    = group_stats["p75"]

    vs_mean_pct = round((sal - mean) / mean * 100, 1) if mean else None

    if sal < p25:
        band = "below_p25"
    elif sal < median:
        band = "p25_median"
    elif sal < p75:
        band = "median_p75"
    else:
        band = "above_p75"

    return {
        "job_salary":   sal,
        "group_mean":   mean,
        "group_median": median,
        "group_p25":    p25,
        "group_p75":    p75,
        "group_count":  group_stats["count"],
        "vs_mean_pct":  vs_mean_pct,
        "band":         band,
    }


# ── Employment terms ──────────────────────────────────────────────────────────

def employment_signals(job: dict) -> dict:
    """Extract employment quality flags."""
    emp  = (job.get("employment_relationship") or "").lower()
    wt   = (job.get("work_time") or "").lower()
    edu  = (job.get("education") or "").lower()

    return {
        "is_permanent": any(k in emp for k in ("unbefristet", "permanent", "festanstellung", "vollzeit")),
        "is_fulltime":  any(k in wt  for k in ("vollzeit", "full", "40")),
        "is_parttime":  any(k in wt  for k in ("teilzeit", "part")),
        "is_temp":      any(k in emp for k in ("befristet", "temporary", "zeitarbeit", "leiharbeit")),
        "has_education_req": bool(edu and edu not in ("n/a", "none", "keine")),
    }


# ── Freshness ────────────────────────────────────────────────────────────────

def freshness_signal(job: dict) -> dict:
    """How recently posted and whether the deadline has passed."""
    today = date.today()

    def _parse(v) -> date | None:
        if not v:
            return None
        if isinstance(v, (date, datetime)):
            return v if isinstance(v, date) else v.date()
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(str(v)[:10], fmt).date()
            except ValueError:
                pass
        return None

    posted   = _parse(job.get("posted"))
    deadline = _parse(job.get("application_deadline"))

    days_old       = (today - posted).days   if posted   else None
    deadline_passed = (deadline < today)     if deadline else False

    return {
        "days_old":        days_old,
        "deadline_passed": deadline_passed,
        "deadline_date":   str(deadline) if deadline else None,
        "freshness_score": max(0.0, 1.0 - (days_old or 30) / 90) if days_old is not None else 0.5,
    }


# ── Responsibilities complexity heuristic ─────────────────────────────────────

def description_complexity(job: dict) -> dict:
    """
    Quick heuristic signals from the description text — fed to the AI as
    structured hints rather than making it re-parse raw HTML/text.
    """
    desc  = str(job.get("description") or job.get("description_snippet") or "")
    skill_count = len(re.findall(r'\b[A-Z][a-zA-Z+#]{2,}\b', desc))  # rough tech-word count
    word_count  = len(desc.split())
    has_leadership = bool(re.search(
        r'\b(leitung|führung|team\s?lead|verantwortlich|manage|koordinier|strateg)',
        desc, re.IGNORECASE,
    ))
    req_years_match = re.search(r'(\d+)\s*\+?\s*(?:jahre?|years?)\s+(?:erfahrung|berufserfahrung|experience)', desc, re.IGNORECASE)
    required_years  = int(req_years_match.group(1)) if req_years_match else None

    return {
        "word_count":      word_count,
        "tech_term_count": skill_count,
        "has_leadership":  has_leadership,
        "required_years":  required_years,
    }


# ── Aggregate bundle for the AI ──────────────────────────────────────────────

def build_quality_context(job: dict, group_stats: dict) -> dict:
    """
    Combine all signals into a single dict that the AI quality classifier
    receives as structured context alongside the raw job text.
    """
    return {
        "completeness":        completeness_score(job),
        "salary_signal":       salary_signal(job, group_stats),
        "employment":          employment_signals(job),
        "freshness":           freshness_signal(job),
        "description_signals": description_complexity(job),
    }
