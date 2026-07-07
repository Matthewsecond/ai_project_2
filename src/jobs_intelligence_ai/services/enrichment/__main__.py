"""
__main__.py — Run seniority + quality classification on real jobs, fetched by id.

    python -m jobs_intelligence_ai.services.enrichment <job_id> [<job_id> ...]
    python -m jobs_intelligence_ai.services.enrichment 12345 --country sk

Fetches the given market job ids (the same JobSearch.fetch the search pipeline
uses between its two stages), then runs classify_seniority + classify_quality on
them and prints each job's resulting fields.
"""
import argparse
import os
import sys


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m jobs_intelligence_ai.services.enrichment",
        description="Classify seniority + quality for real jobs, fetched by id.",
    )
    p.add_argument("job_ids", nargs="+", help="One or more market job ids.")
    p.add_argument("--country", "-c", default=None, help="Country profile, e.g. sk / at.")
    return p.parse_args()


def _force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def main() -> None:
    _force_utf8()
    args = _parse_args()

    if args.country:
        os.environ["COUNTRY"] = args.country.lower()

    from jobs_intelligence_ai.services.search.job_search import JobSearch
    from jobs_intelligence_ai.services.stats import get_group_stats
    from . import classify_seniority, classify_quality

    jobs = JobSearch().fetch(args.job_ids, {})
    if not jobs:
        print("No matching jobs found for those ids.", file=sys.stderr)
        sys.exit(1)

    classify_seniority(jobs)
    for job in jobs:
        group_stats = get_group_stats(job.get("occ_group") or "", job.get("state") or None)
        classify_quality([job], group_stats)

    for job in jobs:
        print(f"[{job['job_id']}] {job['title']} @ {job['company']} "
              f"— seniority={job.get('seniority')} quality={job.get('quality')} "
              f"({job.get('quality_verdict')})")


if __name__ == "__main__":
    main()
