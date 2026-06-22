"""
__main__.py — Run the search module standalone.

    python -m jobs_intelligence_ai.search "Senior Python engineer, Bratislava"
    python -m jobs_intelligence_ai.search "data analyst" --country sk

It searches for the candidate text and prints the matching jobs. The country
profile is taken from --country (or the COUNTRY env var) and applied before the
config-bound modules import.
"""
import argparse
import os
import sys


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m jobs_intelligence_ai.search",
        description="Find the jobs that match a candidate profile.",
    )
    p.add_argument("text", help="Candidate profile: CV text, free description, or key skills.")
    p.add_argument("--country", "-c", default=None, help="Country profile, e.g. sk / at.")
    return p.parse_args()


def _force_utf8() -> None:
    # Windows consoles default to cp1252 and choke on the non-Latin characters
    # that show up in job titles, reasons and skills — print as UTF-8 instead.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _print_jobs(jobs: list[dict]) -> None:
    """Print a ranked job list, one entry (plus its reason) per result."""
    if not jobs:
        print("No matches found.")
        return
    for i, job in enumerate(jobs, 1):
        loc = ", ".join(filter(None, [job.get("city"), job.get("state")])) or "—"
        print(f"{i:>2}. [{job.get('grade', '?')} {job.get('score_pct', '')}] "
              f"{job.get('title', '')} @ {job.get('company', '')} ({loc})")
        if job.get("match_reason"):
            print(f"      {job['match_reason']}")


def main() -> None:
    _force_utf8()
    args = _parse_args()

    # Select the country profile before any config-bound import happens.
    if args.country:
        os.environ["COUNTRY"] = args.country.lower()

    from jobs_intelligence_ai.search.orchestrator import Orchestrator
    from jobs_intelligence_ai.search.exceptions import SearchError

    try:
        jobs = Orchestrator().run(args.text)
    except SearchError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    _print_jobs(jobs)


if __name__ == "__main__":
    main()
