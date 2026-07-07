"""
__main__.py — Generate the AI company-hiring-profile summary for a real company.

    python -m jobs_intelligence_ai.services.reporting "Swiss Re"
    python -m jobs_intelligence_ai.services.reporting "Swiss Re" --country sk

Fetches the company's active postings from the market DB (the same View_Jobs_Full
query the company blueprint runs), computes the aggregate stats summarize_company
expects, and prints the resulting AI summary.

Only company_summary is demoed here — opportunity_briefing / report_generator /
report_pipeline / session_chat take a saved-insights or session payload built up
over a whole browsing session, not a single id, so they aren't a fit for a one-shot
CLI in the same shape as the rest of this package.
"""
import argparse
import os
import statistics
import sys
from collections import Counter


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m jobs_intelligence_ai.services.reporting",
        description="Generate the AI hiring-profile summary for a real company.",
    )
    p.add_argument("company_name", help="Company name as stored in the market DB (crawler name).")
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

    from sqlalchemy import text
    from jobs_intelligence_ai import config
    from jobs_intelligence_ai.infra.database import get_engine
    from .company_summary import summarize_company

    c = config.COL
    col_keys = [k for k in ("title", "salary", "state", "portal", "occ_group")
                if config.PROFILE.col_present(k)]
    cols = ", ".join(f"`{c[k]}`" for k in col_keys)
    sql = f"""
        SELECT {cols} FROM View_Jobs_Full
        WHERE `{c['company']}` LIKE :name AND `{c['status']}` IN ('new', 'updated')
        LIMIT 200
    """
    with get_engine().connect() as conn:
        result = conn.execute(text(sql), {"name": f"%{args.company_name}%"})
        keys = list(result.keys())
        rows = [dict(zip(keys, row)) for row in result]

    if not rows:
        print(f"No active postings found for {args.company_name!r}.", file=sys.stderr)
        sys.exit(1)

    salaries = []
    for r in rows:
        val = r.get(c["salary"])
        if val:
            try:
                v = float(str(val).replace(",", "").replace("€", "").strip())
                if v > 200:
                    salaries.append(v)
            except (ValueError, TypeError):
                pass
    sal_stats = {}
    if salaries:
        sal_stats = {"min": round(min(salaries)), "max": round(max(salaries)),
                     "mean": round(statistics.mean(salaries))}

    title_counts = Counter(r.get(c["title"]) or "" for r in rows)
    title_counts.pop("", None)
    top_titles = [{"title": t, "count": n} for t, n in title_counts.most_common(5)]

    occ_counts = Counter(r.get(c["occ_group"]) or "" for r in rows)
    occ_counts.pop("", None)
    top_occ = [{"group": g, "count": n} for g, n in occ_counts.most_common(4)]

    states = sorted({r.get(c["state"]) or "" for r in rows} - {""})
    portals = sorted({r.get(c["portal"]) or "" for r in rows} - {""})

    summary = summarize_company(
        company_name=args.company_name, total=len(rows),
        top_titles=top_titles, top_occ=top_occ, sal_stats=sal_stats,
        states=states, portals=portals, work_types={},
    )
    if not summary:
        print("No summary produced (missing OPENAI_API_KEY, or the model call failed).",
              file=sys.stderr)
        sys.exit(1)
    print(summary)


if __name__ == "__main__":
    main()
