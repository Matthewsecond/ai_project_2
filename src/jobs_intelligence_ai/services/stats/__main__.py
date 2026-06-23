"""
__main__.py — Show the pure job-quality signals for a sample job (offline, no DB).

    python -m jobs_intelligence_ai.services.stats

Prints the bundled quality context (completeness, salary band, employment, freshness,
description signals) so you can eyeball what the stats service produces. The DB-backed
functions (salary benchmarks, market snapshots) need a live connection and aren't run here.
"""
import json

from .quality_score import build_quality_context

_SAMPLE_JOB = {
    "title": "Senior Python Engineer",
    "description": "Build and maintain REST APIs in Django and FastAPI. 5+ years experience. "
                   "You will lead a small team and own the deployment pipeline.",
    "skills_en": "Python, Django, FastAPI, PostgreSQL, AWS",
    "salary": "4200",
    "url": "https://example.com/jobs/1",
    "contacts": "jobs@example.com",
    "city": "Bratislava",
    "employment_relationship": "Vollzeit, unbefristet",
    "work_time": "Vollzeit",
    "posted": "2026-06-01",
    "application_deadline": "2026-07-15",
}

# Stand-in group stats so the salary band has something to compare against.
_SAMPLE_GROUP_STATS = {"count": 120, "mean": 3800.0, "median": 3700.0, "p25": 3200.0, "p75": 4400.0}


def main() -> None:
    ctx = build_quality_context(_SAMPLE_JOB, _SAMPLE_GROUP_STATS)
    print(json.dumps(ctx, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
