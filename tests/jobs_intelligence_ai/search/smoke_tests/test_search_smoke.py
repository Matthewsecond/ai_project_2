"""
Smoke test for the search module — runs the REAL Orchestrator against the live
OpenAI vector store + MySQL with a candidate profile and PRINTS what comes back,
so we can eyeball how the search behaves. No assertions: it passes if it runs
without blowing up.

Live + slow (real API calls). Defaults to the Slovak profile — override with
COUNTRY=at. Run it and watch the output with:

    COUNTRY=sk python -m pytest tests/jobs_intelligence_ai/search/smoke_tests -s
"""
import os
import sys

# Pick the country profile BEFORE any config-bound import resolves it.
os.environ.setdefault("COUNTRY", "sk")

import pytest

from jobs_intelligence_ai import config
from jobs_intelligence_ai.search.orchestrator import Orchestrator


pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        not config.OPENAI_API_KEY or not config.VECTOR_STORE_ID,
        reason="live smoke test — needs OPENAI_API_KEY and a vector store configured",
    ),
]

# A realistic, full-length candidate profile — the same shape the app's example
# CVs use (history, skills, languages, salary, availability), localized to the
# Slovak dataset so it has something to match against.
PROFILE = """Senior Backend Software Engineer with 6 years of experience building scalable web services, based in Bratislava.

Currently Senior Backend Engineer at a fintech scale-up in Bratislava (2021–present): designing and maintaining REST APIs in Python (Django and FastAPI), running PostgreSQL at scale, deploying microservices on AWS (ECS, Lambda, RDS) via Docker and CI/CD pipelines, and mentoring two junior engineers. Previously Backend Developer at a software house in Bratislava (2018–2021): built payment and reporting integrations, optimised SQL queries and database schemas, and introduced automated testing that cut regression bugs significantly.

Education: Slovak University of Technology in Bratislava — MSc Computer Science (2018).
Key skills: Python, Django, FastAPI, PostgreSQL, REST APIs, microservices, AWS (ECS/Lambda/RDS), Docker, CI/CD, Git, Linux, SQL optimisation, system design.
Languages: Slovak (native), English C1.
Salary expectation: €3,800–4,800 gross/month.
Availability: 2 months notice. Seeking a full-time permanent senior backend role in Bratislava or remote within Slovakia."""


def _run_and_print(profile: str) -> None:
    # Windows consoles default to cp1252 and choke on Slovak diacritics in job text.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print(f"\n=== {config.COUNTRY_LABEL} | profile:\n{profile}\n")
    jobs = None
    for event in Orchestrator().stream(profile):
        if event["event"] == "cycle":
            print(f"  cycle {event['cycle']:>2}  +{event['added']:>2} new ids  total={event['total']}")
        else:
            jobs = event["jobs"]
            print(f"  done: {event['cycles']} cycles, {event['total']} ids -> {len(jobs)} jobs\n")

    for i, j in enumerate(jobs, 1):
        loc = ", ".join(filter(None, [j.get("city"), j.get("state")])) or "—"
        print(f"  {i:>2}. [{j.get('grade')} {j.get('score_pct'):>4}] {j.get('title')} "
              f"@ {j.get('company')} ({loc})")
        if j.get("match_reason"):
            print(f"        {j['match_reason']}")


def test_search_smoke(capsys):
    with capsys.disabled():   # let the live output through regardless of -s
        _run_and_print(PROFILE)


if __name__ == "__main__":
    _run_and_print(PROFILE)
