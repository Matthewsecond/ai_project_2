"""
tabs/company.py — Company profile + salary stats.

Routes:
  GET /api/company          → company hiring profile (jobs, salary, locations, AI summary)
  GET /api/salary_stats     → salary distribution for an occupational group
  GET /api/market/companies → browse the market catalogue's actively-hiring companies
  GET /api/market/contacts  → browse the market catalogue's contacts by name
"""
import statistics
from collections import Counter
from flask import Blueprint, request, jsonify
from jobs_intelligence_ai import config
from jobs_intelligence_ai.infra.database import get_engine
from sqlalchemy import text, bindparam

bp = Blueprint("company", __name__, url_prefix="/api")


def _resolve_company_id(conn, company_name: str):
    """Best-effort market company id for a crawler name, or None.

    Tries three sources in order; each targets a table/column a given country's
    market DB may not have (Slovakia has neither `companies` nor
    View_Jobs_Full.company_id), so each attempt is isolated — one missing table
    must not abort the others (a bare exception rolls back the connection's
    statement, killing later attempts too)."""
    cid = None
    # 1) The exact companies-table id (Austria).
    try:
        cid = conn.execute(text(
            "SELECT id FROM companies WHERE company_crawler_name = :n LIMIT 1"),
            {"n": company_name}).scalar()
    except Exception:
        pass
    # 2) The id the shown jobs carry in the view (covers display-name mismatches).
    if cid is None:
        try:
            cid = conn.execute(text(
                "SELECT company_id FROM View_Jobs_Full "
                "WHERE company_crawler_name = :n AND company_id IS NOT NULL LIMIT 1"),
                {"n": company_name}).scalar()
        except Exception:
            pass
    # 3) Slovakia: company identity lives on the base `jobs` table as
    #    companies_finstat_id (FK -> companies_finstat.id). Read `jobs` directly
    #    (fast) rather than the slow View_Jobs_Full.
    if cid is None:
        try:
            cid = conn.execute(text(
                "SELECT companies_finstat_id FROM jobs "
                "WHERE company_crawler_name = :n "
                "AND companies_finstat_id IS NOT NULL LIMIT 1"),
                {"n": company_name}).scalar()
        except Exception:
            pass
    return int(cid) if cid is not None else None


@bp.route("/company/id", methods=["GET"])
def api_company_id():
    """Query param: name → { ok, company_id }. A lightweight companion to
    /api/company that resolves ONLY the market company id (no jobs fan-out, no
    LLM summary), so the company panel's Save button can light up immediately
    while the full profile still loads in the background."""
    company_name = request.args.get("name", "").strip()
    if not company_name:
        return jsonify({"ok": False, "error": "name required"}), 400
    company_id = None
    try:
        with get_engine().connect() as conn:
            company_id = _resolve_company_id(conn, company_name)
    except Exception:
        pass  # connection-level failure → no id (button stays disabled)
    return jsonify({"ok": True, "company_id": company_id})


@bp.route("/jobs/contacts", methods=["POST"])
def api_jobs_contacts():
    """Body: { job_ids: [..] } → { ok, contacts: { <job_id>: [ {contact_id, name,
    email, phone, linkedin} ] } }. Tries View_Jobs_Contacts first (Austria); falls
    back to the base junction tables for markets without that view — Slovakia has
    no View_Jobs_Contacts at all, so without this fallback every SK job silently
    showed no contact even when contact_jobs_junction/contacts had one (same
    split /api/contact/jobs already uses for the reverse jobs-for-a-contact
    lookup, just missing here until now)."""
    body = request.get_json(silent=True) or {}
    ids  = [int(j) for j in (body.get("job_ids") or []) if str(j).isdigit()][:200]
    out: dict = {}
    if not ids:
        return jsonify({"ok": True, "contacts": out})

    seen: set = set()

    def _add(jid, cid, name, email, phone, linkedin):
        key = (jid, cid)
        if key in seen:
            return
        seen.add(key)
        out.setdefault(jid, []).append({
            "contact_id": int(cid), "name": name or "", "email": email or "",
            "phone": phone or "", "linkedin": linkedin or "",
        })

    try:
        with get_engine().connect() as conn:
            rows = conn.execute(text(
                "SELECT job_id, contact_id, contact_name, contact_email, "
                "  contact_phone, contact_linkedin "
                "FROM View_Jobs_Contacts "
                "WHERE job_id IN :ids AND contact_id IS NOT NULL"
            ).bindparams(bindparam("ids", expanding=True)), {"ids": ids}).mappings().all()
        for r in rows:
            _add(str(r["job_id"]), r["contact_id"], r["contact_name"],
                 r["contact_email"], r["contact_phone"], r["contact_linkedin"])
    except Exception:
        try:
            with get_engine().connect() as conn:
                rows = conn.execute(text(
                    "SELECT cj.job_id AS job_id, c.id AS contact_id, c.name AS name, "
                    "  c.email AS email, c.phone AS phone, c.linkedin AS linkedin "
                    "FROM contact_jobs_junction cj "
                    "JOIN contacts c ON c.id = cj.contact_id "
                    "WHERE cj.job_id IN :ids"
                ).bindparams(bindparam("ids", expanding=True)), {"ids": ids}).mappings().all()
            for r in rows:
                _add(str(r["job_id"]), r["contact_id"], r["name"],
                     r["email"], r["phone"], r["linkedin"])
        except Exception:
            pass  # neither contacts path exists → no contacts
    return jsonify({"ok": True, "contacts": out})


@bp.route("/contact/jobs", methods=["GET"])
def api_contact_jobs():
    """Query param: contact_id → { ok, jobs: [ {job_id, title, company, city, state,
    salary, portal, posted, url, occ_group} ] }. The active jobs a contact is linked
    to (via View_Jobs_Contacts, joined to View_Jobs_Full for the job detail). Guarded
    so a market DB without that view falls back to the base junction tables (Slovakia),
    and returns an empty list if neither path exists."""
    raw = request.args.get("contact_id", "").strip()
    if not raw.isdigit():
        return jsonify({"ok": False, "error": "contact_id required"}), 400
    cid = int(raw)

    c        = config.COL
    col_keys = [k for k in (
        "job_id", "title", "company", "state", "city",
        "salary", "portal", "date_posted", "occ_group", "url",
    ) if config.PROFILE.col_present(k)]

    def _shape(row) -> dict:
        return {
            "job_id":    row.get("job_id"),
            "title":     row.get("title"),
            "company":   row.get("company"),
            "city":      row.get("city"),
            "state":     row.get("state"),
            "salary":    row.get("salary"),
            "portal":    row.get("portal"),
            "posted":    str(row.get("date_posted") or "")[:10] or None,
            "url":       row.get("url"),
            "occ_group": row.get("occ_group"),
        }

    jobs = []
    try:
        cols = ", ".join(f"v.`{c[k]}` AS `{k}`" for k in col_keys)
        sql = f"""
            SELECT DISTINCT {cols}
            FROM View_Jobs_Contacts jc
            JOIN View_Jobs_Full v ON v.`{c['job_id']}` = jc.job_id
            WHERE jc.contact_id = :cid
            ORDER BY v.`{c['date_posted']}` DESC
            LIMIT 100
        """
        with get_engine().connect() as conn:
            rows = conn.execute(text(sql), {"cid": cid}).mappings().all()
        jobs = [_shape(r) for r in rows]
    except Exception:
        # Slovakia (no View_Jobs_Contacts): read via the base junction tables.
        try:
            with get_engine().connect() as conn:
                rows = conn.execute(text(
                    "SELECT DISTINCT j.id AS job_id, j.title AS title, "
                    "  j.company_crawler_name AS company "
                    "FROM contact_jobs_junction cj "
                    "JOIN jobs j ON j.id = cj.job_id "
                    "WHERE cj.contact_id = :cid LIMIT 100"), {"cid": cid}).mappings().all()
            jobs = [_shape(r) for r in rows]
        except Exception:
            pass  # market DB without either contacts path → no jobs
    return jsonify({"ok": True, "jobs": jobs})


def contact_job_counts(contact_ids: list) -> dict[int, int]:
    """Active-job counts for a batch of market contacts → { contact_id: count }.

    Same two-path guard as api_contact_jobs above: View_Jobs_Contacts first,
    then the base junction table (Slovakia); a market DB with neither returns {}.
    Used by the Saved tab to annotate saved contacts with a `job_count`."""
    ids = [int(c) for c in contact_ids if str(c or "").isdigit()]
    if not ids:
        return {}
    for sql in (
        "SELECT contact_id, COUNT(DISTINCT job_id) AS n FROM View_Jobs_Contacts "
        "WHERE contact_id IN :ids GROUP BY contact_id",
        "SELECT contact_id, COUNT(DISTINCT job_id) AS n FROM contact_jobs_junction "
        "WHERE contact_id IN :ids GROUP BY contact_id",
    ):
        try:
            with get_engine().connect() as conn:
                rows = conn.execute(text(sql).bindparams(
                    bindparam("ids", expanding=True)), {"ids": ids}).all()
            return {int(r[0]): int(r[1]) for r in rows}
        except Exception:
            continue  # this country's market DB lacks that table/view — try the next
    return {}


def company_job_counts(company_ids: list) -> dict[int, int]:
    """Active-job counts for a batch of market companies → { company_id: count }.

    Same two-path guard as api_market_companies above: Austria's companies+
    jobs.company_id join first, then Slovakia's jobs.companies_finstat_id fallback
    (no separate companies table there). Used by the Saved tab to annotate saved
    companies with a `job_count` (mirrors contact_job_counts for saved contacts)."""
    ids = [int(c) for c in company_ids if str(c or "").isdigit()]
    if not ids:
        return {}
    for sql in (
        "SELECT co.id AS company_id, COUNT(*) AS n FROM companies co "
        "JOIN jobs j ON j.company_id = co.id AND j.status IN ('new','updated') "
        "WHERE co.id IN :ids GROUP BY co.id",
        "SELECT companies_finstat_id AS company_id, COUNT(*) AS n FROM jobs "
        "WHERE status IN ('new','updated') AND companies_finstat_id IN :ids "
        "GROUP BY companies_finstat_id",
    ):
        try:
            with get_engine().connect() as conn:
                rows = conn.execute(text(sql).bindparams(
                    bindparam("ids", expanding=True)), {"ids": ids}).all()
            return {int(r[0]): int(r[1]) for r in rows}
        except Exception:
            continue  # this country's market DB lacks that shape — try the next
    return {}


@bp.route("/company", methods=["GET"])
def api_company():
    """Query param: name (company name as stored in the DB)"""
    company_name = request.args.get("name", "").strip()
    if not company_name:
        return jsonify({"ok": False, "error": "name required"}), 400

    c    = config.COL
    # Skip columns this country's View_Jobs_Full doesn't have (e.g. SK has no
    # occupational_group); the corresponding row.get(...) below resolves to None.
    col_keys = [k for k in (
        "job_id", "title", "company", "state", "city",
        "salary", "salary_type", "portal", "date_posted",
        "occ_group", "url", "work_time", "employment_relationship",
    ) if config.PROFILE.col_present(k)]
    cols = ", ".join(f"`{c[k]}`" for k in col_keys)

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

        # Market company id (so the panel can save it) + the company's contacts
        # (people linked to its jobs via View_Jobs_Contacts). Guarded: a country
        # whose market DB lacks these just returns no id / no contacts, and the
        # client disables the corresponding Save button.
        company_id = None
        contacts   = []
        try:
            with get_engine().connect() as conn:
                company_id = _resolve_company_id(conn, company_name)

                try:
                    crows = conn.execute(text(
                        "SELECT DISTINCT contact_id, contact_name, contact_email, "
                        "contact_phone, contact_linkedin FROM View_Jobs_Contacts "
                        "WHERE company_crawler_name = :n AND contact_id IS NOT NULL "
                        "ORDER BY contact_name LIMIT 50"), {"n": company_name}).mappings().all()
                    contacts = [{
                        "contact_id": int(r["contact_id"]),
                        "name":       r["contact_name"]     or "",
                        "email":      r["contact_email"]    or "",
                        "phone":      r["contact_phone"]    or "",
                        "linkedin":   r["contact_linkedin"] or "",
                    } for r in crows]
                except Exception:
                    # Slovakia has no View_Jobs_Contacts; read contacts via the base
                    # junction tables instead (fast, no fan-out).
                    try:
                        crows = conn.execute(text(
                            "SELECT DISTINCT c.id AS contact_id, c.name, c.email, "
                            "c.phone, c.linkedin "
                            "FROM contact_jobs_junction cj "
                            "JOIN contacts c ON c.id = cj.contact_id "
                            "JOIN jobs j ON j.id = cj.job_id "
                            "WHERE j.company_crawler_name = :n "
                            "ORDER BY c.name LIMIT 50"), {"n": company_name}).mappings().all()
                        contacts = [{
                            "contact_id": int(r["contact_id"]),
                            "name":       r["name"]     or "",
                            "email":      r["email"]    or "",
                            "phone":      r["phone"]    or "",
                            "linkedin":   r["linkedin"] or "",
                        } for r in crows]
                    except Exception:
                        pass  # market DB without either contacts path → no contacts
        except Exception:
            pass  # e.g. connection-level failure

        from jobs_intelligence_ai.services.reporting import summarize_company
        summary = summarize_company(
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
            "company_id":   company_id,
            "contacts":     contacts,
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


@bp.route("/market/companies", methods=["GET"])
def api_market_companies():
    """Query param: q (optional name substring) → { ok, companies: [{company_id, name,
    job_count}] }, ranked by active-job count. Browses the market catalogue directly —
    independent of a job search — for the Saved tab's "Browse market" mode.

    Tries the Austria shape (companies table + jobs.company_id) first; Slovakia has no
    `companies` table so that query errors and the fallback (jobs.company_crawler_name +
    jobs.companies_finstat_id) is used instead — same isolation pattern as
    _resolve_company_id above."""
    q    = request.args.get("q", "").strip()
    like = f"%{q}%" if q else "%"
    companies = []
    try:
        with get_engine().connect() as conn:
            try:
                rows = conn.execute(text(
                    "SELECT co.id AS company_id, co.company_crawler_name AS name, "
                    "  COUNT(*) AS job_count "
                    "FROM companies co "
                    "JOIN jobs j ON j.company_id = co.id AND j.status IN ('new','updated') "
                    "WHERE co.company_crawler_name LIKE :q "
                    "GROUP BY co.id, co.company_crawler_name "
                    "ORDER BY job_count DESC LIMIT 20"), {"q": like}).mappings().all()
            except Exception:
                rows = conn.execute(text(
                    "SELECT companies_finstat_id AS company_id, company_crawler_name AS name, "
                    "  COUNT(*) AS job_count "
                    "FROM jobs "
                    "WHERE status IN ('new','updated') AND companies_finstat_id IS NOT NULL "
                    "  AND company_crawler_name LIKE :q "
                    "GROUP BY companies_finstat_id, company_crawler_name "
                    "ORDER BY job_count DESC LIMIT 20"), {"q": like}).mappings().all()
        companies = [{"company_id": int(r["company_id"]), "name": r["name"],
                      "job_count": int(r["job_count"])} for r in rows]
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True, "companies": companies})


@bp.route("/market/contacts", methods=["GET"])
def api_market_contacts():
    """Query param: q (required, >= 2 chars) → { ok, contacts: [{contact_id, name, email,
    phone, company}] }. Name search across the market catalogue's contacts, independent of
    a job/company lookup. `company` is best-effort (one of the contact's linked jobs)."""
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify({"ok": True, "contacts": []})
    like = f"%{q}%"
    contacts = []
    try:
        with get_engine().connect() as conn:
            try:
                rows = conn.execute(text(
                    "SELECT c.id, c.name, c.email, c.phone, "
                    "  MIN(co.company_crawler_name) AS company "
                    "FROM contacts c "
                    "LEFT JOIN contact_jobs_junction cj ON cj.contact_id = c.id "
                    "LEFT JOIN jobs j ON j.id = cj.job_id "
                    "LEFT JOIN companies co ON co.id = j.company_id "
                    "WHERE c.name LIKE :q "
                    "GROUP BY c.id, c.name, c.email, c.phone "
                    "ORDER BY c.name LIMIT 20"), {"q": like}).mappings().all()
            except Exception:
                # Slovakia has no `companies` table — the crawler name lives on `jobs` directly.
                rows = conn.execute(text(
                    "SELECT c.id, c.name, c.email, c.phone, "
                    "  MIN(j.company_crawler_name) AS company "
                    "FROM contacts c "
                    "LEFT JOIN contact_jobs_junction cj ON cj.contact_id = c.id "
                    "LEFT JOIN jobs j ON j.id = cj.job_id "
                    "WHERE c.name LIKE :q "
                    "GROUP BY c.id, c.name, c.email, c.phone "
                    "ORDER BY c.name LIMIT 20"), {"q": like}).mappings().all()
        contacts = [{"contact_id": int(r["id"]), "name": r["name"] or "",
                     "email": r["email"] or "", "phone": r["phone"] or "",
                     "company": r["company"] or ""} for r in rows]
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True, "contacts": contacts})


@bp.route("/salary_stats", methods=["GET"])
def api_salary_stats():
    """Query param: occ_group (required)"""
    occ_group = request.args.get("occ_group", "").strip()
    if not occ_group:
        return jsonify({"ok": False, "error": "occ_group required"}), 400

    # Countries without an occupational_group column (e.g. Slovakia) have no
    # group-level salary stats — return an empty result rather than a DB error.
    if not config.PROFILE.col_present("occ_group"):
        return jsonify({"ok": True, "count": 0, "salaries": [], "mean": None, "median": None})

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
