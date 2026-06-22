"""
Stability tests for the search module.

Reproducibility has two independent sources, tested separately so a failure points
at the responsible stage:

  test_retrieval_set_is_stable — Stage 1 only. The direct vector_stores.search id
     set has no model in the loop, so it should be near-identical run to run. Cheap
     (no grading). A failure means RETRIEVAL drifted.

  test_ab_results_overlap — end to end. Runs the full search (retrieve + grade)
     several times for one profile (Peter Varga) and checks how much the A + B
     (strong/good) job-id SETS overlap, via mean pairwise Jaccard. We assert
     overlap, not an identical A+B count: the reasoning grader's scores wobble on
     the 0.60 B/C line, so borderline jobs flip in and out even when retrieval is
     fixed. A failure here, with retrieval stable, means the GRADER drifted.

Live + slow (real API calls). Defaults to the Slovak profile; skipped without an
OpenAI key + vector store. Run it with:

    COUNTRY=sk python -m pytest tests/jobs_intelligence_ai/search/unit_tests/test_search_stability.py -s
"""
import os
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from itertools import combinations

# Pick the country profile BEFORE any config-bound import resolves it.
os.environ.setdefault("COUNTRY", "sk")

import pytest

from jobs_intelligence_ai import config
from jobs_intelligence_ai.services.search.orchestrator import Orchestrator


pytestmark = pytest.mark.skipif(
    not config.OPENAI_API_KEY or not config.VECTOR_STORE_ID,
    reason="live convergence test — needs OPENAI_API_KEY and a vector store configured",
)

# How many independent searches to compare. We check their A+B job-id sets
# substantially overlap. With direct retrieval, Stage 1 is near-deterministic
# (retrieval-set Jaccard ~0.92), so most of the residual variance is the grader.
RUNS = 4

# Minimum mean pairwise Jaccard the A+B id-sets must clear. 0.30 leaves headroom
# for grader jitter at the B/C threshold while still failing loudly if the strong
# core falls apart (broken retrieval/grading pushes overlap toward 0).
MIN_OVERLAP = 0.30

# Minimum mean pairwise Jaccard for the raw RETRIEVAL set (Stage 1 only, no grading).
# Direct search is near-deterministic — measured ~0.92 — so a 0.80 floor catches a
# retrieval regression without tripping on ANN tail jitter.
MIN_RETRIEVAL_OVERLAP = 0.80


def _jaccard(a: set, b: set) -> float:
    """Fraction of the combined set two runs agree on: |a∩b| / |a∪b|."""
    return len(a & b) / len(a | b) if (a or b) else 1.0

# Peter Varga — from the app's example candidates (web/templates/index.html).
PETER_VARGA = """B2B Sales Manager with 10 years of experience in enterprise software and SaaS sales, based in Bratislava.

Currently Senior Account Executive at CloudSoft Slovakia s.r.o. (2020–present): managing 35 enterprise accounts (€2.0M ARR), consistently exceeding quota 115–130% per year, running the full sales cycle from outreach to close. Previously Account Manager at BusinessSoft a.s. Bratislava (2016–2020): grew SME revenue by 40% over 3 years, introduced Salesforce CRM, mentored two junior reps. Inside Sales Rep at TeleSolutions Slovakia (2014–2016): 200+ cold calls/week, exceeded quota 18 of 24 months.

Education: University of Economics in Bratislava – Ing. Business Administration (2014).
Key skills: B2B sales, SaaS, enterprise account management, Salesforce CRM, pipeline management, contract negotiation, consultative selling, upsell/cross-sell.
Languages: Slovak (native), English C1, Hungarian B2.
Salary expectation: €2,500–3,200 gross/month + variable.
Availability: 3 months notice. Open to Sales Manager or Head of Sales roles in Slovakia."""


def _search_once(engine: Orchestrator) -> tuple[list[dict], int]:
    """Run one full search, returning (jobs, cycles)."""
    jobs, cycles = [], 0
    for event in engine.stream(PETER_VARGA):
        if event["event"] == "done":
            jobs, cycles = event["jobs"], event["cycles"]
    return jobs, cycles


def test_ab_results_overlap(capsys):
    engine = Orchestrator()
    assert engine.config.direct_retrieval, "this test exercises the direct-retrieval Stage 1"
    engine._ensure_ready()   # warm the shared client before launching parallel runs

    # Run the searches concurrently — they're I/O-bound on the API, so this is
    # ~RUNS× faster than running them one after another. The Orchestrator keeps no
    # mutable state between calls, so one shared instance is safe across threads.
    with ThreadPoolExecutor(max_workers=RUNS) as ex:
        outcomes = list(ex.map(lambda _: _search_once(engine), range(RUNS)))

    ab_sets = []
    with capsys.disabled():
        for stream in (sys.stdout, sys.stderr):   # Slovak diacritics → UTF-8
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

        print(f"\n=== {config.COUNTRY_LABEL} | A+B overlap over {RUNS} runs | Peter Varga\n")
        for run, (jobs, cycles) in enumerate(outcomes, 1):
            grades = Counter(j["grade"] for j in jobs)
            ab = sorted((j for j in jobs if j["grade"] in ("A", "B")),
                        key=lambda j: j["score"], reverse=True)
            ab_sets.append({j["job_id"] for j in ab})
            print(f"run {run}: {cycles} pass(es) | total {len(jobs)} | "
                  f"A={grades['A']} B={grades['B']} C={grades['C']}  ->  A+B={len(ab)}")
            for j in ab:
                print(f"    [{j['grade']} {j['score_pct']:>4}] {j['title']} @ {j['company']}")

        # Overlap of the A+B job-id sets is the quality signal. The 4-way core is
        # the jobs that surfaced in EVERY run; mean pairwise Jaccard is the smoother
        # per-pair agreement we assert on.
        core      = set.intersection(*ab_sets) if ab_sets else set()
        pairwise  = [_jaccard(a, b) for a, b in combinations(ab_sets, 2)]
        mean_jac  = sum(pairwise) / len(pairwise) if pairwise else 1.0
        print(f"\ncore (A+B in all {RUNS} runs): {len(core)} ids {sorted(core)}")
        print(f"mean pairwise Jaccard: {mean_jac:.2f}  "
              f"(per-pair: {[round(j, 2) for j in pairwise]})")

    # Recall sanity — each run must find a real strong list.
    assert min(len(s) for s in ab_sets) >= 3, (
        f"a run returned too few A+B matches: {[len(s) for s in ab_sets]}"
    )
    # Reproducibility — the strong sets must substantially agree run to run.
    assert mean_jac >= MIN_OVERLAP, (
        f"A+B job-id sets did not converge across {RUNS} runs "
        f"(mean pairwise Jaccard {mean_jac:.2f} < {MIN_OVERLAP}): {ab_sets}"
    )


def test_retrieval_set_is_stable(capsys):
    """Stage 1 only: the direct vector_stores.search id set should be near-identical
    run to run. Cheap (no grading), so it isolates a RETRIEVAL regression from the
    grader jitter that test_ab_results_overlap deliberately tolerates."""
    engine = Orchestrator()
    assert engine.config.direct_retrieval, "this test exercises the direct-retrieval Stage 1"
    engine._ensure_ready()

    # search_scored() is one deterministic API call — no model in the loop, no grading.
    id_sets = [frozenset(jid for jid, _ in engine._embedding.search_scored(PETER_VARGA))
               for _ in range(RUNS)]

    pairwise = [_jaccard(set(a), set(b)) for a, b in combinations(id_sets, 2)]
    mean_jac = sum(pairwise) / len(pairwise) if pairwise else 1.0
    core     = set.intersection(*map(set, id_sets)) if id_sets else set()

    with capsys.disabled():
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
        print(f"\n=== {config.COUNTRY_LABEL} | retrieval-set stability over {RUNS} runs\n")
        print(f"sizes {[len(s) for s in id_sets]} | core in all runs {len(core)} | "
              f"mean pairwise Jaccard {mean_jac:.2f} "
              f"(per-pair {[round(j, 2) for j in pairwise]})")

    # Recall sanity — retrieval must return a real candidate set.
    assert min(len(s) for s in id_sets) >= 10, (
        f"retrieval returned too few ids: {[len(s) for s in id_sets]}"
    )
    # Determinism — the id set must be near-identical across runs.
    assert mean_jac >= MIN_RETRIEVAL_OVERLAP, (
        f"retrieval set not stable across {RUNS} runs "
        f"(mean pairwise Jaccard {mean_jac:.2f} < {MIN_RETRIEVAL_OVERLAP})"
    )
