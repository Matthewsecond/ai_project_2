"""
tabs/job_detail.py — Job Detail modal (routes used when a job card is opened).

Routes:
  POST /api/job_chat              → chat about a single job
  POST /api/job_chat/reset        → clear per-job chat session
  POST /api/desc_translate        → translate job description to English
  POST /api/desc_compact          → summarise job description (3-4 sentences)
  POST /api/desc_cv_questions     → generate gap-based interview questions
  POST /api/desc_outreach         → write candidate outreach message
  POST /api/candidate_strength    → score candidate against job on 5 dimensions
"""
import json as _json
import re
from flask import Blueprint, request, jsonify
from jobs_intelligence_ai import config
from jobs_intelligence_ai.core import send_job_message, clear_job_session

bp = Blueprint("job_detail", __name__, url_prefix="/api")


@bp.route("/job_chat", methods=["POST"])
def api_job_chat():
    """Body: { session_id, message, job_context?: dict, candidate_text?: str, lang?: str }"""
    body           = request.get_json(silent=True) or {}
    session_id     = body.get("session_id", "").strip()
    message        = body.get("message", "").strip()
    job_context    = body.get("job_context", {})
    candidate_text = (body.get("candidate_text") or body.get("cv_text") or "").strip()
    lang           = body.get("lang", "en")

    if not message:
        return jsonify({"ok": False, "error": "message required"}), 400
    if not session_id:
        return jsonify({"ok": False, "error": "session_id required"}), 400

    try:
        result = send_job_message(session_id, message, job_context, lang=lang,
                                  candidate_text=candidate_text)
        return jsonify({"ok": True, **result})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


@bp.route("/job_chat/reset", methods=["POST"])
def api_job_chat_reset():
    body       = request.get_json(silent=True) or {}
    session_id = body.get("session_id", "").strip()
    clear_job_session(session_id)
    return jsonify({"ok": True})


@bp.route("/desc_translate", methods=["POST"])
def api_desc_translate():
    """Body: { description }  →  { ok, text } (English translation)"""
    body        = request.get_json(silent=True) or {}
    description = body.get("description", "").strip()
    if not description:
        return jsonify({"ok": False, "error": "description required"}), 400
    try:
        from jobs_intelligence_ai.core import get_client
        client   = get_client()
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


@bp.route("/desc_compact", methods=["POST"])
def api_desc_compact():
    """Body: { description, lang? }  →  { ok, text } (3-4 sentence summary)"""
    body        = request.get_json(silent=True) or {}
    description = body.get("description", "").strip()
    lang        = body.get("lang", "de")
    if not description:
        return jsonify({"ok": False, "error": "description required"}), 400
    lang_note = " Respond in English." if lang == "en" else ""
    try:
        from jobs_intelligence_ai.core import get_client
        client   = get_client()
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


@bp.route("/desc_cv_questions", methods=["POST"])
def api_desc_cv_questions():
    """Body: { description, cv_text, lang? }  →  { ok, text } (gap-based interview questions)"""
    body        = request.get_json(silent=True) or {}
    description = body.get("description", "").strip()
    cv_text     = body.get("cv_text", "").strip()
    lang        = body.get("lang", "de")
    if not description or not cv_text:
        return jsonify({"ok": False, "error": "description and cv_text required"}), 400
    lang_note = " Write all questions and notes in English." if lang == "en" else ""
    try:
        from jobs_intelligence_ai.core import get_client
        client = get_client()
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


@bp.route("/desc_outreach", methods=["POST"])
def api_desc_outreach():
    """Body: { job: dict, candidate_name?, cv_text?, lang? }  →  { ok, text }"""
    body           = request.get_json(silent=True) or {}
    job            = body.get("job", {})
    candidate_name = body.get("candidate_name", "").strip()
    cv_text        = body.get("cv_text", "").strip()
    lang           = body.get("lang", "de")
    if not job.get("title"):
        return jsonify({"ok": False, "error": "job.title required"}), 400
    lang_note = " Write the message in English." if lang == "en" else ""
    try:
        from jobs_intelligence_ai.core import get_client
        client        = get_client()
        candidate_line = f"Candidate name: {candidate_name}" if candidate_name else "No candidate name provided."
        cv_line        = f"Candidate background (from CV):\n{cv_text}" if cv_text else "No CV provided."
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


@bp.route("/candidate_strength", methods=["POST"])
def api_candidate_strength():
    """
    Body: { job: dict, cv_text, lang? }
    Returns: { ok, axes, scores, reasons, overall }
    """
    body    = request.get_json(silent=True) or {}
    job     = body.get("job", {})
    cv_text = body.get("cv_text", "").strip()
    lang    = body.get("lang", "de")
    if not cv_text or not job.get("title"):
        return jsonify({"ok": False, "error": "job.title and cv_text required"}), 400
    lang_note = " Respond in English." if lang == "en" else ""
    try:
        from jobs_intelligence_ai.core import get_client
        client = get_client()
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
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = _json.loads(raw)
        return jsonify({"ok": True, **parsed})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500
