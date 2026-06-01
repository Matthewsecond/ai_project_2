"""
app.py — Jobs Intelligence AI Sales Tool (Demo / Real DB version)
Flask backend with simulated AI matching + real MySQL data.

Run:
    python app.py
Then open: http://localhost:5000
"""
import re
import statistics
from datetime import date
from functools import wraps
from flask import Flask, jsonify, request, render_template, abort, session, redirect, url_for
import config
from core.database import get_filter_options, describe_view, get_engine
from core.matching import run_matching
from core.chat import send_message, clear_session, send_job_message, clear_job_session, enrich_jobs_from_db
from sqlalchemy import text

app = Flask(__name__)
app.json.sort_keys = False   # preserve key order in responses
app.secret_key = "jia-demo-secret-2024-xK9pLm"   # change in production

# ── Auth setup ────────────────────────────────────────────────────────────────
from helpers.auth import init_db, verify_login
init_db()   # create users.db + seed accounts on first run

# Routes that don't need a login check
_PUBLIC_ENDPOINTS = {"login", "static"}

@app.before_request
def require_login():
    """Redirect unauthenticated users to the login page."""
    if request.endpoint in _PUBLIC_ENDPOINTS:
        return
    if "user_id" not in session:
        if request.is_json or (request.path.startswith("/api/")):
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        return redirect(url_for("login"))

# In-memory saved jobs store (resets on server restart — good enough for demo)
_saved_jobs: list[dict] = []


# ─── Login / logout ──────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        user = verify_login(username, password)
        if user:
            session.clear()
            session["user_id"]      = user["id"]
            session["username"]     = user["username"]
            session["display_name"] = user["display_name"]
            session["role"]         = user["role"]
            return redirect(url_for("index"))
        error = "Incorrect username or password."
    return render_template(
        "login.html",
        error=error,
        prefill_user="admin",
        prefill_pass="admin",
        year=date.today().year,
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ─── Main page ────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template(
        "index.html",
        current_user=session.get("display_name") or session.get("username", ""),
    )


# ─── API: filter options ──────────────────────────────────────────────────────

@app.route("/api/filters")
def api_filters():
    """Return distinct values for all filter dropdowns."""
    try:
        options = get_filter_options()
        return jsonify({"ok": True, "data": options})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ─── API: run matching ────────────────────────────────────────────────────────

@app.route("/api/match", methods=["POST"])
def api_match():
    """
    Body (JSON):
      {
        "candidate_text": "...",   // CV text, free-text profile, or assembled query
        "filters": {               // all optional
          "state":     "Wien",
          "occ_group": "IT",
          "portal":    "AMS",
          "city":      "Wien"
        },
        "top_n": 20                // optional, max 50
      }
    Returns ranked job list with score, grade, match_reason.
    """
    body = request.get_json(silent=True) or {}
    candidate_text = body.get("candidate_text", "").strip()
    filters        = body.get("filters", {})
    top_n          = int(body.get("top_n", config.DEFAULT_TOP_N))

    if not candidate_text:
        return jsonify({"ok": False, "error": "candidate_text is required"}), 400

    try:
        results = run_matching(candidate_text, filters, top_n)
        return jsonify({
            "ok":     True,
            "count":  len(results),
            "top_n":  top_n,
            "jobs":   results,
        })
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


# ─── API: saved jobs (in-memory pipeline) ────────────────────────────────────

@app.route("/api/saved", methods=["GET"])
def api_saved_get():
    return jsonify({"ok": True, "count": len(_saved_jobs), "jobs": _saved_jobs})


@app.route("/api/saved", methods=["POST"])
def api_saved_add():
    """Add a job to the saved pipeline. Body: { job: {...}, status: 'New' }"""
    body = request.get_json(silent=True) or {}
    job  = body.get("job")
    if not job:
        return jsonify({"ok": False, "error": "job required"}), 400

    job_id = job.get("job_id")
    # Avoid duplicates
    if any(j.get("job_id") == job_id for j in _saved_jobs):
        return jsonify({"ok": True, "message": "Already saved", "jobs": _saved_jobs})

    entry = {**job, "pipeline_status": body.get("status", "New"), "notes": "", "extras": body.get("extras") or {}}
    _saved_jobs.append(entry)
    return jsonify({"ok": True, "count": len(_saved_jobs), "jobs": _saved_jobs})


@app.route("/api/saved/<job_id>", methods=["PATCH"])
def api_saved_update(job_id):
    """Update status, notes, or extras for a saved job."""
    body = request.get_json(silent=True) or {}
    for job in _saved_jobs:
        if job.get("job_id") == job_id:
            if "pipeline_status" in body:
                job["pipeline_status"] = body["pipeline_status"]
            if "notes" in body:
                job["notes"] = body["notes"]
            if "extras" in body:
                job["extras"] = {**(job.get("extras") or {}), **body["extras"]}
            return jsonify({"ok": True, "job": job})
    return jsonify({"ok": False, "error": "Not found"}), 404


@app.route("/api/saved/report", methods=["POST"])
def api_saved_report():
    """Generate a PDF report for the saved jobs pipeline including extras."""
    from flask import make_response
    from helpers.report_pipeline import generate_saved_jobs_pdf
    body = request.get_json(silent=True) or {}
    jobs = body.get("jobs") or _saved_jobs
    candidate_profile = body.get("candidate_profile") or None
    if not jobs:
        return jsonify({"ok": False, "error": "No saved jobs"}), 400
    try:
        pdf_bytes = generate_saved_jobs_pdf(jobs, candidate_profile=candidate_profile)
        # Derive filename from candidate name
        cand_name = None
        if candidate_profile and candidate_profile.get("name"):
            cand_name = candidate_profile["name"]
        elif jobs and jobs[0].get("candidate_name"):
            cand_name = jobs[0]["candidate_name"]
        if cand_name:
            safe_name = re.sub(r"[^\w\s-]", "", cand_name).strip().replace(" ", "_")
        else:
            safe_name = "Candidate"
        filename = f"{safe_name}_JobsAI.pdf"

        resp = make_response(pdf_bytes)
        resp.headers["Content-Type"] = "application/pdf"
        resp.headers["Content-Disposition"] = f"attachment; filename={filename}"
        return resp
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/api/saved/<job_id>", methods=["DELETE"])
def api_saved_delete(job_id):
    """Remove a job from the pipeline."""
    global _saved_jobs
    before = len(_saved_jobs)
    _saved_jobs = [j for j in _saved_jobs if j.get("job_id") != job_id]
    removed = before - len(_saved_jobs)
    return jsonify({"ok": True, "removed": removed, "count": len(_saved_jobs)})


# ─── API: chat ───────────────────────────────────────────────────────────────

@app.route("/api/chat", methods=["POST"])
def api_chat():
    """
    Body: { "session_id": "...", "message": "..." }
    Returns: { "ok": true, "text": "...", "jobs": [...] }
    """
    body       = request.get_json(silent=True) or {}
    session_id  = body.get("session_id", "default")
    message     = body.get("message", "").strip()
    lang        = body.get("lang", "auto")
    filters     = body.get("filters") or {}
    max_results = int(body.get("max_results", 20))
    if not message:
        return jsonify({"ok": False, "error": "message required"}), 400
    try:
        result = send_message(session_id, message, lang=lang,
                              filters=filters, max_results=max_results)
        result["jobs"] = enrich_jobs_from_db(result.get("jobs") or [])
        return jsonify({"ok": True, **result})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/api/quality", methods=["POST"])
def api_quality():
    """
    Assess quality for a batch of jobs.
    Body: { jobs: [...], occ_group: str, state: str | null }
    Each job needs at minimum: title, description (or snippet), salary, skills.
    Returns: { ok, jobs: [...enriched with quality fields] }
    """
    body      = request.get_json(silent=True) or {}
    jobs      = body.get("jobs") or []
    occ_group = body.get("occ_group") or ""
    state     = body.get("state") or None

    if not jobs:
        return jsonify({"ok": False, "error": "jobs array required"}), 400

    try:
        from stats.salary_stats import get_group_stats
        from helpers.quality_classifier import classify_quality

        group_stats = get_group_stats(occ_group, state) if occ_group else {}
        result_jobs = classify_quality(list(jobs), group_stats)
        return jsonify({"ok": True, "jobs": result_jobs, "group_stats": group_stats})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/api/chat/reset", methods=["POST"])
def api_chat_reset():
    """Clear the conversation history for a session."""
    body       = request.get_json(silent=True) or {}
    session_id = body.get("session_id", "default")
    clear_session(session_id)
    return jsonify({"ok": True})


# ─── API: job-specific chat ────────────────────────────────────────────────────

@app.route("/api/job_chat", methods=["POST"])
def api_job_chat():
    """
    Chat about a single job. Body: { session_id, message, job_context: {...} }
    Returns: { ok, text }
    """
    body        = request.get_json(silent=True) or {}
    session_id  = body.get("session_id", "").strip()
    message     = body.get("message", "").strip()
    job_context = body.get("job_context", {})
    lang        = body.get("lang", "en")
    if not message:
        return jsonify({"ok": False, "error": "message required"}), 400
    if not session_id:
        return jsonify({"ok": False, "error": "session_id required"}), 400
    try:
        result = send_job_message(session_id, message, job_context, lang=lang)
        return jsonify({"ok": True, **result})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/api/job_chat/reset", methods=["POST"])
def api_job_chat_reset():
    body       = request.get_json(silent=True) or {}
    session_id = body.get("session_id", "").strip()
    clear_job_session(session_id)
    return jsonify({"ok": True})


# ─── API: description utilities ───────────────────────────────────────────────

@app.route("/api/desc_translate", methods=["POST"])
def api_desc_translate():
    body = request.get_json(silent=True) or {}
    description = body.get("description", "").strip()
    if not description:
        return jsonify({"ok": False, "error": "description required"}), 400
    try:
        from core.chat import _get_client
        client = _get_client()
        response = client.responses.create(
            model=config.CHAT_MODEL,
            instructions=(
                "You are a professional translator. "
                "Translate the following job description to English. "
                "Output only the translated text, preserving the original structure and line breaks."
            ),
            input=description[:4000],
        )
        return jsonify({"ok": True, "text": response.output_text or ""})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/api/desc_compact", methods=["POST"])
def api_desc_compact():
    body = request.get_json(silent=True) or {}
    description = body.get("description", "").strip()
    lang        = body.get("lang", "de")
    if not description:
        return jsonify({"ok": False, "error": "description required"}), 400
    lang_note = " Respond in English." if lang == "en" else ""
    try:
        from core.chat import _get_client
        client = _get_client()
        response = client.responses.create(
            model=config.CHAT_MODEL,
            instructions=(
                "Summarize the following job description in 3-4 sentences. "
                "Cover: the role and main responsibilities, key required skills or experience, "
                "and salary or benefits if mentioned. Be concise and informative. "
                f"Output only the summary, nothing else.{lang_note}"
            ),
            input=description[:4000],
        )
        return jsonify({"ok": True, "text": response.output_text or ""})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/api/desc_cv_questions", methods=["POST"])
def api_desc_cv_questions():
    body        = request.get_json(silent=True) or {}
    description = body.get("description", "").strip()
    cv_text     = body.get("cv_text", "").strip()
    lang        = body.get("lang", "de")
    if not description or not cv_text:
        return jsonify({"ok": False, "error": "description and cv_text required"}), 400
    lang_note = " Write all questions and notes in English." if lang == "en" else ""
    try:
        from core.chat import _get_client
        client = _get_client()
        prompt = (
            f"JOB DESCRIPTION:\n{description[:3000]}\n\n"
            f"CANDIDATE CV:\n{cv_text[:3000]}"
        )
        response = client.responses.create(
            model=config.CHAT_MODEL,
            instructions=(
                "You are a recruitment assistant. Compare the job description and the candidate CV. "
                "Identify gaps or areas where the candidate's experience may not fully match the role. "
                "Generate 5-7 targeted interview questions that probe those gaps. "
                "For each question add a brief one-line note (in parentheses) explaining the gap it addresses. "
                f"Use a numbered list. Output only the questions, nothing else.{lang_note}"
            ),
            input=prompt,
        )
        return jsonify({"ok": True, "text": response.output_text or ""})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/api/desc_outreach", methods=["POST"])
def api_desc_outreach():
    body           = request.get_json(silent=True) or {}
    job            = body.get("job", {})
    candidate_name = body.get("candidate_name", "").strip()
    cv_text        = body.get("cv_text", "").strip()
    lang           = body.get("lang", "de")
    if not job.get("title"):
        return jsonify({"ok": False, "error": "job.title required"}), 400
    lang_note = " Write the message in English." if lang == "en" else ""
    try:
        from core.chat import _get_client
        client = _get_client()
        candidate_line = f"Candidate name: {candidate_name}" if candidate_name else "No candidate name provided."
        cv_line = f"Candidate background (from CV):\n{cv_text}" if cv_text else "No CV provided."
        prompt = (
            f"Job title: {job.get('title', '—')}\n"
            f"Company: {job.get('company', '—')}\n"
            f"Location: {job.get('location', '—')}\n"
            f"Salary: {job.get('salary') or 'not specified'}\n"
            f"Key skills: {job.get('skills') or 'not specified'}\n"
            f"Job description excerpt: {(job.get('description') or '')[:800]}\n\n"
            f"{candidate_line}\n"
            f"{cv_line}"
        )
        response = client.responses.create(
            model=config.CHAT_MODEL,
            instructions=(
                "You are a recruiter writing a brief outreach message to a candidate about a job opportunity. "
                "Write 3-4 sentences: mention the role and company, highlight one or two genuinely appealing aspects "
                "of the position, and end with a clear call to action (e.g. ask if they are open to a quick chat). "
                "If a candidate name is provided, address them by first name. "
                "If CV details are provided, personalise one sentence to their background. "
                f"Keep the tone professional but warm. Output only the message text, no subject line or sign-off.{lang_note}"
            ),
            input=prompt,
        )
        return jsonify({"ok": True, "text": response.output_text or ""})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/api/candidate_strength", methods=["POST"])
def api_candidate_strength():
    import json as _json
    body    = request.get_json(silent=True) or {}
    job     = body.get("job", {})
    cv_text = body.get("cv_text", "").strip()
    lang    = body.get("lang", "de")
    if not cv_text or not job.get("title"):
        return jsonify({"ok": False, "error": "job.title and cv_text required"}), 400
    lang_note = " Respond in English." if lang == "en" else ""
    try:
        from core.chat import _get_client
        client = _get_client()
        prompt = (
            f"JOB TITLE: {job.get('title','—')}\n"
            f"COMPANY: {job.get('company','—')}\n"
            f"REQUIRED SKILLS: {job.get('skills') or 'not specified'}\n"
            f"JOB DESCRIPTION:\n{(job.get('description') or '')[:1500]}\n\n"
            f"CANDIDATE CV:\n{cv_text[:1500]}"
        )
        response = client.responses.create(
            model=config.CHAT_MODEL,
            instructions=(
                "You are a recruitment analyst. Score the candidate against the job on exactly these "
                "5 dimensions: Skills Match, Experience Level, Education Fit, Salary Alignment, Location Fit. "
                "Score each 0–10 (10 = perfect fit). Provide a one-sentence reason for each score. "
                "Also write one overall sentence summarising the fit. "
                f"Return ONLY valid JSON in this exact shape, nothing else:{lang_note}\n"
                '{"axes":["Skills Match","Experience Level","Education Fit","Salary Alignment","Location Fit"],'
                '"scores":[<int>,<int>,<int>,<int>,<int>],'
                '"reasons":["<str>","<str>","<str>","<str>","<str>"],'
                '"overall":"<str>"}'
            ),
            input=prompt,
        )
        raw = (response.output_text or "").strip()
        # strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = _json.loads(raw)
        return jsonify({"ok": True, **parsed})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


# ─── API: opportunity radar ───────────────────────────────────────────────────

@app.route("/api/opportunity")
def api_opportunity():
    """
    Returns all data for the Opportunity Radar tab.
    Optional query params:
      briefing=1   — include AI-generated briefing (default: 1)
      weeks=8      — weeks for volume trend
      state        — filter by Bundesland
      portal       — filter by job portal
      occ_group    — filter by occupational group
      min_salary   — filter to jobs with salary >= N
    """
    include_briefing = request.args.get("briefing", "1") != "0"
    weeks = int(request.args.get("weeks", 8))

    # Collect scope filters (empty string → None so queries skip them)
    # Single-value filters (manual dropdowns)
    filters = {
        k: request.args.get(k) or None
        for k in ("state", "portal", "occ_group", "min_salary")
    }
    filters = {k: v for k, v in filters.items() if v}

    # Multi-value filters (from AI filter assist) — sent as repeated params
    _occ_groups = [g for g in request.args.getlist("occ_groups") if g]
    _states     = [s for s in request.args.getlist("states")     if s]
    _portals    = [p for p in request.args.getlist("portals")    if p]
    if _occ_groups: filters["occ_groups"] = _occ_groups
    if _states:     filters["states"]     = _states
    if _portals:    filters["portals"]    = _portals

    try:
        from stats.opportunity import (
            get_sector_snapshot, get_state_snapshot, get_portal_snapshot,
            get_volume_trend, get_summary_totals,
        )

        sectors  = get_sector_snapshot(limit=40, filters=filters)
        states   = get_state_snapshot(filters=filters)
        portals  = get_portal_snapshot(filters=filters)
        trend    = get_volume_trend(weeks=weeks, filters=filters)
        totals   = get_summary_totals(filters=filters)

        briefing = {}
        if include_briefing:
            from helpers.opportunity_briefing import generate_briefing
            briefing = generate_briefing(sectors, states, portals, trend, totals)

        return jsonify({
            "ok":      True,
            "totals":  totals,
            "sectors": sectors,
            "states":  states,
            "portals": portals,
            "trend":   trend,
            "briefing": briefing,
            "filters": filters,   # echo active filters back to client
        })
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/api/opportunity/jobs")
def api_opportunity_jobs():
    """
    Stale or urgent jobs for the Quick Finder sub-view.
    Query params:
      mode      = stale | urgent   (default: stale)
      min_days  = int              (default: 45, stale mode)
      deadline  = int              (default: 14, urgent mode)
      occ_group = str              (optional filter)
      state     = str              (optional filter)
      portal    = str              (optional filter)
      limit     = int              (default: 50)
    """
    mode      = request.args.get("mode", "stale")
    limit     = int(request.args.get("limit", 50))
    occ_group = request.args.get("occ_group") or None
    state     = request.args.get("state") or None
    portal    = request.args.get("portal") or None

    try:
        from stats.opportunity import get_stale_jobs, get_urgent_jobs
        if mode == "urgent":
            deadline = int(request.args.get("deadline", 14))
            jobs = get_urgent_jobs(deadline_days=deadline, limit=limit)
        else:
            min_days = int(request.args.get("min_days", 45))
            jobs = get_stale_jobs(
                min_days=min_days, limit=limit,
                occ_group=occ_group, state=state, portal=portal
            )
        return jsonify({"ok": True, "count": len(jobs), "jobs": jobs})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


# ─── API: AI filter suggestion ───────────────────────────────────────────────

@app.route("/api/opportunity/filter-assist", methods=["POST"])
def api_opportunity_filter_assist():
    """
    Map a free-text query to concrete filter selections using the LLM.

    POST body (JSON):
      query   : str          — natural language description
      sectors : list[str]    — available occupational groups (from /api/filters)
      states  : list[str]    — available states
      portals : list[str]    — available portals

    Returns: { ok, occ_groups, states, portals, min_salary, explanation, count_hint }
    """
    data    = request.get_json(silent=True) or {}
    query   = (data.get("query") or "").strip()
    sectors = data.get("sectors") or []
    states  = data.get("states")  or []
    portals = data.get("portals") or []

    if not query:
        return jsonify({"ok": False, "error": "query is required"}), 400

    try:
        from helpers.opportunity_briefing import suggest_filters
        result = suggest_filters(query, sectors, states, portals)
        return jsonify({"ok": True, **result})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


# ─── API: Radar follow-up chat ───────────────────────────────────────────────

@app.route("/api/opportunity/chat", methods=["POST"])
def api_opportunity_chat():
    """
    Multi-turn chat grounded in the current Radar briefing + stats snapshot.

    POST body (JSON):
      message : str                  — user's question
      history : [{role, content}]    — prior turns (last ~8 kept)
      context : dict                 — briefing + totals + sectors snapshot
    """
    data    = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    history = data.get("history") or []
    context = data.get("context") or {}

    if not message:
        return jsonify({"ok": False, "error": "message required"}), 400
    if not config.OPENAI_API_KEY:
        return jsonify({"ok": False, "error": "OpenAI API key not configured"}), 503

    try:
        from openai import OpenAI
        client = OpenAI(api_key=config.OPENAI_API_KEY)

        system = _build_radar_chat_system(context)

        messages = [{"role": "system", "content": system}]
        for h in history[-8:]:   # keep last 8 turns for context window
            if h.get("role") in ("user", "assistant") and h.get("content"):
                messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": message})

        resp = client.chat.completions.create(
            model=config.CHAT_MODEL,
            messages=messages,
            max_completion_tokens=600,
            temperature=0.65,
        )
        answer = resp.choices[0].message.content or ""
        return jsonify({"ok": True, "answer": answer})

    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


# ─── API: Analytics session report (PDF) ─────────────────────────────────────

@app.route("/api/analytics/report", methods=["POST"])
def api_analytics_report():
    """
    Generate an AI-elaborated PDF report from saved summary items.

    POST body (JSON):
      items   : list of {type, label, content}
      context : briefing + totals snapshot
      charts  : optional list of {title, data_url} — base64 PNG chart images
    """
    data    = request.get_json(silent=True) or {}
    items   = data.get("items") or []
    context = data.get("context") or {}
    charts  = data.get("charts") or []

    if not items:
        return jsonify({"ok": False, "error": "No items provided"}), 400

    try:
        from helpers.report_generator import elaborate_items, generate_pdf
        elaborated = elaborate_items(items, context)
        pdf_bytes  = generate_pdf(elaborated, context, charts=charts)

        from flask import Response
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": 'attachment; filename="analytics-report.pdf"',
                "Content-Length": str(len(pdf_bytes)),
            },
        )
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


# ─── API: Example candidate CV PDF ──────────────────────────────────────────

@app.route("/api/candidate/example-pdf", methods=["GET"])
def api_example_cv():
    """Return Anna Bauer example CV as a downloadable PDF."""
    from helpers.example_cv import generate_example_cv_pdf
    from flask import Response
    pdf_bytes = generate_example_cv_pdf()
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="Anna_Bauer_CV.pdf"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )


@app.route("/api/candidate/example-pdf-2", methods=["GET"])
def api_example_cv_2():
    """Return Max Weber example CV as a downloadable PDF."""
    from helpers.example_cv import generate_example_cv_pdf_2
    from flask import Response
    pdf_bytes = generate_example_cv_pdf_2()
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="Max_Weber_CV.pdf"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )


# ─── API: Parse uploaded CV PDF ──────────────────────────────────────────────

@app.route("/api/candidate/parse-pdf", methods=["POST"])
def api_parse_pdf():
    """
    Extract plain text from an uploaded PDF CV.
    Returns { ok, text } where text is up to 8 000 characters.
    """
    f = request.files.get("file")
    if not f:
        return jsonify({"ok": False, "error": "No file uploaded"}), 400
    try:
        from pypdf import PdfReader
        reader = PdfReader(f.stream)
        pages_text = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                pages_text.append(t.strip())
        text = "\n\n".join(pages_text)[:8000]
        return jsonify({"ok": True, "text": text})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


# ─── API: Parse candidate profile with AI ────────────────────────────────────

_PROFILE_SYSTEM = """\
You are a CV parser. Extract structured information from the candidate text below.
Return ONLY valid JSON — no prose, no code fences:
{
  "name": "Full name or null",
  "title": "Current or most recent job title or null",
  "experience_years": "e.g. '8 years' or null",
  "skills": ["up to 8 key skills"],
  "location": "City or region or null",
  "languages": "e.g. 'German (native), English B2' or null",
  "salary_expectation": "e.g. '€2,800–3,400/month' or null",
  "availability": "e.g. 'Immediately' or null",
  "summary": "One concise sentence describing this candidate's profile"
}
"""


@app.route("/api/candidate/parse-profile", methods=["POST"])
def api_parse_profile():
    """
    Extract structured candidate info from raw CV/profile text using AI.
    POST body: { text: str }
    Returns: { ok, name, title, experience_years, skills, location, languages,
                salary_expectation, availability, summary }
    """
    import re, json as _json
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "No text provided"}), 400
    if not config.OPENAI_API_KEY:
        return jsonify({"ok": False, "error": "OpenAI API key not configured"}), 503

    try:
        from openai import OpenAI
        client = OpenAI(api_key=config.OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model=config.CLASSIFIER_MODEL,
            messages=[
                {"role": "system", "content": _PROFILE_SYSTEM},
                {"role": "user",   "content": text[:4000]},
            ],
            max_completion_tokens=400,
            temperature=0.1,
        )
        raw = (resp.choices[0].message.content or "").strip()
        raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
        result = _json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError("Expected JSON object")
        return jsonify({"ok": True, **result})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


# ─── API: Analytics summary chat ─────────────────────────────────────────────

@app.route("/api/analytics/chat", methods=["POST"])
def api_analytics_chat():
    """
    Multi-turn chat grounded in the user's saved summary items.

    POST body (JSON):
      history : [{role, content}]          — prior turns
      items   : list of {type, label, content}  — saved summary items
    """
    data    = request.get_json(silent=True) or {}
    history = data.get("history") or []
    items   = data.get("items") or []

    if not history:
        return jsonify({"ok": False, "error": "history required"}), 400
    if not config.OPENAI_API_KEY:
        return jsonify({"ok": False, "error": "OpenAI API key not configured"}), 503

    try:
        from openai import OpenAI
        client = OpenAI(api_key=config.OPENAI_API_KEY)

        system = _build_summary_chat_system(items)
        messages = [{"role": "system", "content": system}]
        for h in history[-10:]:
            if h.get("role") in ("user", "assistant") and h.get("content"):
                messages.append({"role": h["role"], "content": h["content"]})

        resp = client.chat.completions.create(
            model=config.CHAT_MODEL,
            messages=messages,
            max_completion_tokens=600,
            temperature=0.55,
        )
        answer = resp.choices[0].message.content or ""
        return jsonify({"ok": True, "answer": answer})

    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


def _build_radar_chat_system(ctx: dict) -> str:
    """Serialize the radar snapshot into a system prompt for follow-up chat."""
    lines = [
        "You are a recruitment advisor helping HR professionals in Austria understand their job market.",
        "Your audience is HR managers and recruiters — not data analysts. They need clear, actionable guidance.",
        "",
        "Tone and format rules (follow strictly):",
        "- Lead every answer with the key action or decision, then briefly explain why using 1-2 numbers.",
        "- Never open with a statistic. Open with what the person should DO or KNOW.",
        "- Use plain business language. Avoid jargon like 'backlog-conversion', 'top-of-funnel', 'stale demand'.",
        "  Say 'unfilled for 30+ days' not 'stale'. Say 'harder to fill' not 'underserved'.",
        "- Keep it to 2-3 short paragraphs. No walls of text.",
        "- Use **bold** for the most important figures or action words (markdown will be rendered).",
        "- Use bullet points only when listing 3+ parallel items.",
        "- If the data does not contain what was asked, say so in one sentence.",
        "",
        "=== MARKET SNAPSHOT ===",
    ]

    t = ctx.get("totals") or {}
    if t:
        lines += [
            f"Active jobs      : {t.get('total_active','?')}",
            f"Stale 30+ days   : {t.get('stale_30','?')}  ({round(t.get('stale_30',0)/max(t.get('total_active',1),1)*100)}%)",
            f"Stale 60+ days   : {t.get('stale_60','?')}",
            f"Urgent ≤14 days  : {t.get('urgent_14d','?')}",
            f"Sectors tracked  : {t.get('sector_count','?')}",
        ]

    if ctx.get("headline"):
        lines += ["", f"Headline: {ctx['headline']}"]

    if ctx.get("top_opportunities"):
        lines += ["", "Top opportunities:"]
        for o in ctx["top_opportunities"][:6]:
            lines.append(f"  • {o.get('label')} — {o.get('reason')} [signal:{o.get('signal')}]")

    if ctx.get("underserved"):
        lines += ["", "Underserved markets:"]
        for u in ctx["underserved"][:4]:
            lines.append(f"  • {u.get('label')} — {u.get('reason')}")

    if ctx.get("urgency_alerts"):
        lines += ["", "Urgency alerts:"]
        for u in ctx["urgency_alerts"][:4]:
            lines.append(f"  • {u.get('label')}: {u.get('count')} jobs, {u.get('note','')}")

    if ctx.get("trend_summary"):
        lines += ["", f"Volume trend: {ctx['trend_summary']}"]

    if ctx.get("recommendations"):
        lines += ["", "Recommendations:"]
        for i, r in enumerate(ctx["recommendations"][:5], 1):
            lines.append(f"  {i}. {r}")

    if ctx.get("top_sectors"):
        lines += ["", "Top sectors (by volume):"]
        for s in ctx["top_sectors"][:8]:
            sal = f"€{s.get('avg_salary'):,}" if s.get("avg_salary") else "—"
            lines.append(
                f"  • {s.get('occ_group')}: {s.get('total_jobs')} jobs, "
                f"{s.get('stale_30',0)} stale30, {s.get('urgent_deadline',0)} urgent, avg {sal}"
            )

    if ctx.get("filters"):
        lines += ["", f"Active scope filters: {ctx['filters']}"]

    return "\n".join(lines)


def _build_summary_chat_system(items: list) -> str:
    """System prompt for the Analytics Summary assistant chat."""
    type_names = {
        "recommendation": "Recommendation",
        "opportunity":    "Top Opportunity",
        "underserved":    "Underserved Market",
        "urgency":        "Urgency Alert",
        "trend":          "Trend Insight",
        "chat":           "Chat Insight",
    }
    lines = [
        "You are an expert HR analytics assistant helping an HR professional in Austria prepare their session report.",
        "The user has saved the following insights during their analytics session:",
        "",
    ]
    for i, item in enumerate(items, 1):
        tname = type_names.get(item.get("type", "chat"), "Insight")
        preview = (item.get("content") or "")[:200]
        lines.append(f"{i}. [{tname}] {item.get('label','')} — {preview}")

    lines += [
        "",
        "Your role: help the user think through the report — what to include, what's most important,",
        "how to frame findings, suggest a logical order, or clarify any of the data points.",
        "Be concise and direct. These are HR professionals, not data analysts.",
        "Use **bold** for key points or figures (markdown will be rendered).",
        "Keep responses to 3 short paragraphs max.",
    ]
    return "\n".join(lines)


# ─── API: company profile ────────────────────────────────────────────────────

@app.route("/api/company", methods=["GET"])
def api_company():
    """
    Return a company's hiring profile pulled live from the DB.
    Query param: name  (exact company name as it appears in the results table)
    Returns: job count, salary stats, top titles, locations, AI summary, recent jobs.
    """
    import statistics as _stats
    from collections import Counter

    company_name = request.args.get("name", "").strip()
    if not company_name:
        return jsonify({"ok": False, "error": "name required"}), 400

    c = config.COL
    cols = ", ".join(f"`{c[k]}`" for k in [
        "job_id", "title", "company", "state", "city",
        "salary", "salary_type", "portal", "date_posted",
        "occ_group", "url", "work_time", "employment_relationship",
    ])

    def _fetch(company_param, use_like=False):
        op  = "LIKE" if use_like else "="
        val = f"%{company_param}%" if use_like else company_param
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
            keys = list(result.keys())
            return [dict(zip(keys, row)) for row in result]

    try:
        rows = _fetch(company_name)
        if not rows:
            rows = _fetch(company_name, use_like=True)

        if not rows:
            return jsonify({"ok": True, "company": company_name, "total_jobs": 0,
                            "salary_stats": {}, "locations": [], "states": [],
                            "top_titles": [], "top_occ": [], "portals": [],
                            "date_range": {}, "work_types": {},
                            "recent_jobs": [], "summary": ""})

        # ── Salary stats ──────────────────────────────────────────────────────
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
            salaries = salaries[:max(1, int(len(salaries) * 0.98))]  # drop top 2% outliers
            sal_stats = {
                "min":    round(min(salaries)),
                "max":    round(max(salaries)),
                "mean":   round(_stats.mean(salaries)),
                "median": round(_stats.median(salaries)),
                "count":  len(salaries),
            }

        # ── Locations ─────────────────────────────────────────────────────────
        states = sorted({r.get(c["state"]) or "" for r in rows} - {""})
        cities = sorted({r.get(c["city"]) or "" for r in rows} - {""})

        # ── Role breakdown ────────────────────────────────────────────────────
        title_counts = Counter(r.get(c["title"]) or "" for r in rows)
        title_counts.pop("", None)
        top_titles = [{"title": t, "count": n} for t, n in title_counts.most_common(8)]

        occ_counts = Counter(r.get(c["occ_group"]) or "" for r in rows)
        occ_counts.pop("", None)
        occ_counts.pop("keine Zuordnung", None)
        top_occ = [{"group": g, "count": n} for g, n in occ_counts.most_common(6)]

        # ── Other metadata ────────────────────────────────────────────────────
        portals    = sorted({r.get(c["portal"]) or "" for r in rows} - {""})
        work_types = Counter(r.get(c["work_time"]) or "" for r in rows)
        work_types.pop("", None)

        dates = sorted(
            str(r.get(c["date_posted"]) or "")[:10]
            for r in rows if r.get(c["date_posted"])
        )
        date_range = {"oldest": dates[0] if dates else None,
                      "newest": dates[-1] if dates else None}

        # ── Recent jobs list (up to 10) ───────────────────────────────────────
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

        # ── AI summary ────────────────────────────────────────────────────────
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


def _company_summary(company_name, total, top_titles, top_occ, sal_stats, states, portals, work_types):
    """Ask the LLM for a 2-3 sentence hiring-profile summary of a company."""
    if not config.OPENAI_API_KEY:
        return ""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=config.OPENAI_API_KEY)
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


# ─── API: salary stats ────────────────────────────────────────────────────────

@app.route("/api/salary_stats")
def api_salary_stats():
    """
    Returns salary distribution for a given occupational group.
    Query params: occ_group (required)
    Returns: { ok, count, salaries: [float], mean, median }
    """
    occ_group = request.args.get("occ_group", "").strip()
    if not occ_group:
        return jsonify({"ok": False, "error": "occ_group required"}), 400

    c = config.COL
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
            raw = [float(row[0]) for row in result if row[0] and float(row[0]) > 200]
        if not raw:
            return jsonify({"ok": True, "count": 0, "salaries": [], "mean": None, "median": None})
        # remove extreme outliers (top 2%)
        raw.sort()
        cut = int(len(raw) * 0.98)
        salaries = raw[:cut]
        mean   = round(statistics.mean(salaries), 0)
        median = round(statistics.median(salaries), 0)
        return jsonify({"ok": True, "count": len(salaries), "salaries": salaries,
                        "mean": mean, "median": median})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ─── Test fixtures endpoint ───────────────────────────────────────────────────

@app.route("/api/test/match")
def api_test_match():
    """Return hardcoded fixture jobs — lets you test the modal without a real search."""
    from test.fixtures import SAMPLE_JOBS
    return jsonify({"ok": True, "count": len(SAMPLE_JOBS), "top_n": len(SAMPLE_JOBS), "jobs": SAMPLE_JOBS})


# ─── Test: job detail view ────────────────────────────────────────────────────

@app.route("/test/job-detail")
@app.route("/test/job-detail/<int:n>")
def test_job_detail(n: int = 0):
    """
    Standalone page that opens the job detail modal pre-loaded with fixture job N.
    Use to visually inspect the modal layout, salary chart, skills, and chat.
    e.g.  /test/job-detail/0  → Staplerfahrer
          /test/job-detail/1  → Software Developer
          /test/job-detail/2  → Koch
    """
    from test.fixtures import SAMPLE_JOBS
    from core.job_detail import JobDetail
    job = JobDetail.from_dict(SAMPLE_JOBS[n % len(SAMPLE_JOBS)])
    all_jobs = [JobDetail.from_dict(j).to_dict() for j in SAMPLE_JOBS]
    return render_template(
        "job_detail_test.html",
        job=job.to_dict(),
        all_jobs=all_jobs,
        n=n,
        total=len(SAMPLE_JOBS),
    )


# ─── Debug endpoint ────────────────────────────────────────────────────────────

@app.route("/debug/schema")
def debug_schema():
    """
    Returns DESCRIBE View_Jobs_Full — use this on first startup to verify
    actual column names and update COL mapping in config.py if needed.
    """
    try:
        schema = describe_view()
        return jsonify({"ok": True, "columns": schema})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n  Jobs Intelligence AI - Demo Server")
    print(f"  http://localhost:{config.FLASK_PORT}")
    print(f"  Schema debug: http://localhost:{config.FLASK_PORT}/debug/schema\n")
    app.run(
        host="0.0.0.0",
        port=config.FLASK_PORT,
        debug=config.FLASK_DEBUG,
    )
