"""
__main__.py — Verify a login, or list users, from the command line (real app DB).

    python -m jobs_intelligence_ai.services.auth <username> <password>
    python -m jobs_intelligence_ai.services.auth --list

Runs init_db() first (creates + seeds account_company/app_user if the app DB is
empty, same as the app does on startup), then verifies the given credentials —
or lists every user with --list.
"""
import argparse
import json
import sys


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m jobs_intelligence_ai.services.auth",
        description="Verify a login (or list users) against the app DB.",
    )
    p.add_argument("username", nargs="?", help="Username to verify.")
    p.add_argument("password", nargs="?", help="Password to verify.")
    p.add_argument("--list", action="store_true", help="List all users instead of verifying one.")
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

    from . import init_db, verify_login, list_users

    init_db()

    if args.list:
        print(json.dumps(list_users(), indent=2, ensure_ascii=False))
        return

    if not args.username or not args.password:
        print("Usage: python -m jobs_intelligence_ai.services.auth <username> <password>",
              file=sys.stderr)
        print("       python -m jobs_intelligence_ai.services.auth --list", file=sys.stderr)
        sys.exit(1)

    user = verify_login(args.username, args.password)
    if user is None:
        print("Invalid credentials.", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(user, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
