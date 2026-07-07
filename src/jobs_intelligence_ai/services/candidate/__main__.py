"""
__main__.py — Parse a structured candidate profile from raw CV/free text.

    python -m jobs_intelligence_ai.services.candidate "Jane Doe, 8 years in ..."
    python -m jobs_intelligence_ai.services.candidate --file cv.txt

Runs the same Structured-Outputs call the search tab's "paste a CV" path uses
(parse_candidate_profile) and prints the resulting profile as JSON.
"""
import argparse
import json
import sys


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m jobs_intelligence_ai.services.candidate",
        description="Parse a structured candidate profile from raw CV/free text.",
    )
    p.add_argument("text", nargs="?", help="Raw CV / candidate description text.")
    p.add_argument("--file", help="Read the text from a file instead of the command line.")
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

    if args.file:
        cv_text = open(args.file, encoding="utf-8").read()
    elif args.text:
        cv_text = args.text
    else:
        print("Usage: python -m jobs_intelligence_ai.services.candidate <text> | --file <path>",
              file=sys.stderr)
        sys.exit(1)

    from .profile_parser import parse_candidate_profile

    try:
        profile = parse_candidate_profile(cv_text)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(profile, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
