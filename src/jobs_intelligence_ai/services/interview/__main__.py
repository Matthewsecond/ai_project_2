"""
__main__.py — Generate interview questions for a real job + a candidate CV.

    python -m jobs_intelligence_ai.services.interview <job_id> --candidate-text "..."
    python -m jobs_intelligence_ai.services.interview <job_id> --cv-file cv.txt

Fetches the job row from the market DB (the same JobSearch.fetch the search
pipeline uses) and runs InterviewHelper.generate_questions against the given
candidate CV text.
"""
import argparse
import os
import sys


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m jobs_intelligence_ai.services.interview",
        description="Generate interview questions for a real job + a candidate CV.",
    )
    p.add_argument("job_id", help="Market job id to fetch.")
    p.add_argument("--candidate-text", default="", help="Candidate CV / profile text.")
    p.add_argument("--cv-file", help="Read the candidate CV text from a file.")
    p.add_argument("--country", "-c", default=None, help="Country profile, e.g. sk / at.")
    p.add_argument("--lang", default="en", help="Question language (default: en).")
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
    if not cv_text.strip():
        print("A candidate CV is required: --candidate-text \"...\" or --cv-file <path>",
              file=sys.stderr)
        sys.exit(1)

    from jobs_intelligence_ai.services.search.job_search import JobSearch
    from . import InterviewHelper

    jobs = JobSearch().fetch([args.job_id], {})
    if not jobs:
        print(f"No job found for id {args.job_id!r}.", file=sys.stderr)
        sys.exit(1)

    result = InterviewHelper().generate_questions(jobs[0], cv_text, lang=args.lang)
    if not result.get("ok"):
        print(f"Error: {result.get('error')}", file=sys.stderr)
        sys.exit(1)

    for q in result["questions"]:
        print(f"- {q['question']}")
        if q.get("note"):
            print(f"    ({q['note']})")


if __name__ == "__main__":
    main()
