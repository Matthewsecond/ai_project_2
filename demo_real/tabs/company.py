"""
tabs/company.py — Company profile + salary stats.

Routes:
  GET /api/company        → company hiring profile (jobs, salary, locations, AI summary)
  GET /api/salary_stats   → salary distribution for an occupational group
"""
import statistics
from collections import Counter
from flask import Blueprint, request, jsonify
import config
from core.database import get_engine
from sqlalchemy import text

bp = Blueprint("company", __name__, url_prefix="/api")


@bp.route("/company", methods=["GET"])
def api_company():
    """Query param: name (company name as stored in the DB)"""
    company_name = request.args.get("name", "").strip()
    if not company_name:
        return jsonify({"ok": False, "error": "name required"}), 400

    c    = config.COL
    cols = ", ".join(f"`{c[k]}`" for k in [
        "job_id", "title", "company", "state", "city",
        "salary", "salary_type", "portal", "date_posted",
        "occ_group", "url", "work_time", "employment_relationship",
    ])

    def _fetch(param, use_like=False):
        op  = "LIKE" if use_like else "="
        val = f"%{param}%" if use_like else param
        sql = f"""
            SELECT {cols}
            FROM View_Jobs_Full
            WHERE `{c['company']}` {op} :company
              AND `{c['status']}` IN ('new', 'updated')
            ORDER BY `{c['date_posted']}` DESC
            LIMIT 100
        """
        with get_engine().connect() as conn:
            result = conn.execute(text(sql), {"company": val})
            keys   = list(result.keys())
            return [dict(zip(keys, row)) for row in result]

    try:
        rows = _fetch(company_name) or _fetch(company_name, use_like=True)

        if not rows:
            return jsonify({"ok": True, "company": company_name, "total_jobs": 0,
                            "salary_stats": {}, "locations": [], "states": [],
                            "top_titles": [], "top_occ": [], "portals": [],
                            "date_range": {}, "work_types": {},
                            "recent_jobs": [], "summary": ""})

        # Salary stats
        salaries = []
        for row in rows:
            val = row.get(c["salary"])
            if val:
                try:
                    v = float(str(val).replace(",", "").replace("€", "").strip())
                    if v > 200:
                        salaries.append(v)
                except (ValueError, TypeError):
                    pass
        sal_stats: dict = {}
        if salaries:
            salaries.sort()
            salaries  = salaries[:max(1, int(len(salaries) * 0.98))]
            sal_stats = {
                "min":    round(min(salaries)),
                "max":    round(max(salaries)),
                "mean":   round(statistics.mean(salaries)),
                "median": round(statistics.median(salaries)),
                "count":  len(salaries),
            }

        states = sorted({r.get(c["state"]) or "" for r in rows} - {""})
        cities = sorted({r.get(c["city"])  or "" for r in rows} - {""})

        title_counts = Counter(r.get(c["title"]) or "" for r in rows)
        title_counts.pop("", None)
        top_titles = [{"title": t, "count": n} for t, n in title_counts.most_common(8)]

        occ_counts = Counter(r.get(c["occ_group"]) or "" for r in rows)
        occ_counts.pop("", None)
        occ_counts.pop("keine Zuordnung", None)
        top_occ = [{"group": g, "count": n} for g, n in occ_counts.most_common(6)]

        portals    = sorted({r.get(c["portal"]) or "" for r in rows} - {""})
        work_types = Counter(r.get(c["work_time"]) or "" for r in rows)
        work_types.pop("", None)

        dates = sorted(
            str(r.get(c["date_posted"]) or "")[:10]
            for r in rows if r.get(c["date_posted"])
        )
        date_range = {"oldest": dates[0] if dates else None, "newest": dates[-1] if dates else None}

        recent_jobs = [
            {
                "job_id":    row.get(c["job_id"]),
                "title":     row.get(c["title"]),
                "city":      row.get(c["city"]),
                "state":     row.get(c["state"]),
                "salary":    row.get(c["salary"]),
                "portal":    row.get(c["portal"]),
                "posted":    str(row.get(c["date_posted"]) or "")[:10] or None,
                "url":       row.get(c["url"]),
                "occ_group": row.get(c["occ_group"]),
            }
            for row in rows[:10]
        ]

        summary = _company_summary(
            company_name=company_name,
            total=len(rows),
            top_titles=top_titles,
            top_occ=top_occ,
            sal_stats=sal_stats,
            states=states,
            portals=portals,
            work_types=dict(work_types.most_common(4)),
        )

        return jsonify({
            "ok":           True,
            "company":      company_name,
            "total_jobs":   len(rows),
            "salary_stats": sal_stats,
            "locations":    cities[:12],
            "states":       states,
            "top_titles":   top_titles,
            "top_occ":      top_occ,
            "portals":      portals,
            "date_range":   date_range,
            "work_types":   dict(work_types.most_common(5)),
            "recent_jobs":  recent_jobs,
            "summary":      summary,
        })

    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


@bp.route("/salary_stats", methods=["GET"])
def api_salary_stats():
    """Query param: occ_group (required)"""
    occ_group = request.args.get("occ_group", "").strip()
    if not occ_group:
        return jsonify({"ok": False, "error": "occ_group required"}), 400

    c   = config.COL
    sql = f"""
        SELECT CAST(`{c['salary']}` AS DECIMAL(10,2)) AS sal
        FROM View_Jobs_Full
        WHERE `{c['occ_group']}` = :occ
          AND `{c['salary']}` IS NOT NULL
          AND `{c['salary']}` != ''
          AND CAST(`{c['salary']}` AS DECIMAL(10,2)) > 200
        LIMIT 1000
    """
    try:
        with get_engine().connect() as conn:
            result = conn.execute(text(sql), {"occ": occ_group})
            raw    = [float(row[0]) for row in result if row[0] and float(row[0]) > 200]
        if not raw:
            return jsonify({"ok": True, "count": 0, "salaries": [], "mean": None, "median": None})
        raw.sort()
        salaries = raw[:int(len(raw) * 0.98)]
        return jsonify({
            "ok":       True,
            "count":    len(salaries),
            "salaries": salaries,
            "mean":     round(statistics.mean(salaries), 0),
            "median":   round(statistics.median(salaries), 0),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── AI helper ────────────────────────────────────────────────────────────────

def _company_summary(company_name, total, top_titles, top_occ, sal_stats, states, portals, work_types):
    if not config.OPENAI_API_KEY:
        return ""
    try:
        from openai import OpenAI
        client     = OpenAI(api_key=config.OPENAI_API_KEY)
        titles_str = ", ".join(f"{t['title']} ×{t['count']}" for t in top_titles[:5])
        occ_str    = ", ".join(f"{o['group']} ({o['count']})" for o in top_occ[:4])
        sal_str    = (
            f"€{sal_stats['min']:,}–€{sal_stats['max']:,}, average €{sal_stats['mean']:,}"
            if sal_stats else "not disclosed"
        )
        prompt = (
            f"Company: {company_name}\n"
            f"Active job postings: {total}\n"
            f"Top roles: {titles_str or '—'}\n"
            f"Occupational groups: {occ_str or '—'}\n"
            f"Salary range: {sal_str}\n"
            f"Active states: {', '.join(states[:5]) if states else '—'}\n"
            f"Job portals: {', '.join(portals) if portals else '—'}\n"
            f"Work types: {', '.join(f'{k} ({v})' for k, v in work_types.items()) or '—'}\n"
        )
        resp = client.chat.completions.create(
            model=config.CLASSIFIER_MODEL,
            messages=[
                {"role": "system", "content": (
                    "You are a recruitment intelligence assistant. "
                    "Write 2-3 concise sentences summarising this company's current hiring profile "
                    "for an HR professional. Cover: what type of company it appears to be based on "
                    "the roles, where they operate, and what salaries they offer. "
                    "Be factual and direct. Output only the summary, nothing else."
                )},
                {"role": "user", "content": prompt},
            ],
            max_completion_tokens=160,
            temperature=0.25,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        return ""
