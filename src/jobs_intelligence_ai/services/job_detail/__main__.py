"""
__main__.py — Run one of the Job Detail modal's AI tools against a real job.

    python -m jobs_intelligence_ai.services.job_detail <job_id> --op compact
    python -m jobs_intelligence_ai.services.job_detail <job_id> --op cv-questions --candidate-text "..."
    python -m jobs_intelligence_ai.services.job_detail <job_id> --op strength --cv-file cv.txt

Fetches the job row from the market DB (the same JobSearch.fetch the search
pipeline uses) and runs one of: translate, compact, cv-questions, outreach,
strength (default: compact).
"""
import argparse
import json
import os
import sys

_OPS = ("translate", "compact", "cv-questions", "outreach", "strength")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m jobs_intelligence_ai.services.job_detail",
        description="Run one of the Job Detail modal's AI tools against a real job.",
    )
    p.add_argument("job_id", help="Market job id to fetch.")
    p.add_argument("--op", choices=_OPS, default="compact", help="Which tool to run (default: compact).")
    p.add_argument("--candidate-text", default="", help="Candidate CV text (cv-questions/outreach/strength).")
    p.add_argument("--cv-file", help="Read the candidate CV text from a file.")
    p.add_argument("--candidate-name", default="", help="Candidate name (outreach only).")
    p.add_argument("--country", "-c", default=None, help="Country profile, e.g. sk / at.")
    p.add_argument("--lang", default="en", help="Output language (default: en).")
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

    cv_text = open(args.cv_file, encoding="utf-8").read() if args.cv_file else args.candidate_text

    from jobs_intelligence_ai.services.search.job_search import JobSearch
    from . import (
        translate_description, compact_description, generate_cv_questions,
        write_outreach, score_candidate_strength,
    )

    jobs = JobSearch().fetch([args.job_id], {})
    if not jobs:
        print(f"No job found for id {args.job_id!r}.", file=sys.stderr)
        sys.exit(1)
    job = jobs[0]
    description = job.get("description") or job.get("summary") or ""

    try:
        if args.op == "translate":
            result = translate_description(description)
        elif args.op == "compact":
            result = compact_description(description, args.lang)
        elif args.op == "cv-questions":
            result = generate_cv_questions(description, cv_text, args.lang)
        elif args.op == "outreach":
            result = write_outreach(job, args.candidate_name, cv_text, args.lang)
        else:  # strength
            result = score_candidate_strength(job, cv_text, args.lang)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if isinstance(result, dict):
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(result)


if __name__ == "__main__":
    main()
