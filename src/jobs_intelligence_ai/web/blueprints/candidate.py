"""
tabs/candidate.py — Candidate CV management.

Routes:
  GET  /api/candidate/example-pdf    → download Anna Bauer example CV PDF (AT)
  GET  /api/candidate/example-pdf-2  → download Max Weber example CV PDF (AT)
  GET  /api/candidate/example-pdf-sk → download Marek Novák example CV PDF (SK)
  POST /api/candidate/parse-pdf      → extract text from an uploaded PDF
  POST /api/candidate/parse-profile  → parse structured profile from raw text using AI
"""
import re
import json as _json
from flask import Blueprint, request, jsonify, Response
from jobs_intelligence_ai import config

bp = Blueprint("candidate", __name__, url_prefix="/api/candidate")

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
  "email": "email address or null",
  "phone": "phone number or null",
  "linkedin": "full LinkedIn profile URL or null",
  "summary": "One concise sentence describing this candidate's profile"
}
"""


@bp.route("/example-pdf", methods=["GET"])
def api_example_cv():
    from jobs_intelligence_ai.services.example_cv import generate_example_cv_pdf
    pdf_bytes = generate_example_cv_pdf()
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="Anna_Bauer_CV.pdf"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )


@bp.route("/example-pdf-2", methods=["GET"])
def api_example_cv_2():
    from jobs_intelligence_ai.services.example_cv import generate_example_cv_pdf_2
    pdf_bytes = generate_example_cv_pdf_2()
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="Max_Weber_CV.pdf"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )


@bp.route("/example-pdf-sk", methods=["GET"])
def api_example_cv_sk():
    """Slovak example CV PDF (Marek Novák) — used by the SK build."""
    from jobs_intelligence_ai.services.example_cv import generate_example_cv_pdf_sk
    pdf_bytes = generate_example_cv_pdf_sk()
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="Marek_Novak_CV.pdf"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )


_MAX_ENRICH_URLS = 25


@bp.route("/enrich-linkedin", methods=["POST"])
def api_enrich_linkedin():
    """Body: { urls: [..] } (or { url } for one) → enrich LinkedIn profiles via Apify.

    Returns { ok, count, requested, profiles:[{profile, text}] } — each `profile` is
    the app's candidate-profile shape (drives the card + save), `text` a CV-like blob
    for matching. Multiple URLs are enriched in a single actor run.
    """
    data = request.get_json(silent=True) or {}
    raw  = data.get("urls")
    if raw is None and data.get("url"):
        raw = [data["url"]]
    urls = [u.strip() for u in (raw or []) if isinstance(u, str) and u.strip()]
    if not urls:
        return jsonify({"ok": False, "error": "No URL(s) provided"}), 400
    if any("linkedin.com/" not in u.lower() for u in urls):
        return jsonify({"ok": False, "error": "All URLs must be LinkedIn profile URLs"}), 400
    if len(urls) > _MAX_ENRICH_URLS:
        return jsonify({"ok": False,
                        "error": f"Too many URLs — max {_MAX_ENRICH_URLS} per run"}), 400
    if not config.APIFY_API_KEY:
        return jsonify({"ok": False, "error": "Apify API key not configured"}), 503

    from jobs_intelligence_ai.integrations.linkedin import enrich_linkedin, map_to_profile, to_candidate_text
    from jobs_intelligence_ai.services.profile_enricher import enrich_linkedin_profile
    try:
        items = enrich_linkedin(urls)
        # The scraper returns one item per URL; failed ones carry an `errorMessage`
        # (deleted / private / not-found profile) and no name. Drop those so they
        # don't become blank candidate cards — `requested` vs `count` shows the gap.
        good = [it for it in (items or [])
                if it.get("full_name") and not it.get("errorMessage")]
        if not good:
            msg = (items[0].get("errorMessage") if items else None) \
                  or "No data returned for those profiles"
            return jsonify({"ok": False, "error": msg}), 404
        profiles = []
        for it in good:
            # Mechanical map = accurate structured base; AI then analyzes the raw
            # scrape and layers on inferred fields (seniority, salary, summary, …).
            base = map_to_profile(it)
            prof = enrich_linkedin_profile(it, base=base)
            profiles.append({"profile": prof, "text": to_candidate_text(it, base)})
        return jsonify({"ok": True, "count": len(profiles),
                        "requested": len(urls), "profiles": profiles})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


@bp.route("/parse-pdf", methods=["POST"])
def api_parse_pdf():
    """Upload a PDF file; returns { ok, text } (up to 8 000 chars)."""
    f = request.files.get("file")
    if not f:
        return jsonify({"ok": False, "error": "No file uploaded"}), 400
    try:
        from pypdf import PdfReader
        reader     = PdfReader(f.stream)
        pages_text = [t.strip() for page in reader.pages if (t := page.extract_text())]
        text       = "\n\n".join(pages_text)[:8000]
        return jsonify({"ok": True, "text": text})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


@bp.route("/assistant", methods=["POST"])
def api_candidate_assistant():
    """
    Main-page candidate assistant.

    Body: { session_id, message, profile?, jobs?, lang? }
      - profile : current candidate-profile dict shown on the card
      - jobs    : list of offers currently matched on screen (lastResults)
    Returns: { ok, reply, profile_updates, cv_note }
      - profile_updates : partial profile dict to merge into the card
      - cv_note         : one CV-style line to append to the CV text for re-matching
    """
    data       = request.get_json(silent=True) or {}
    message    = (data.get("message") or "").strip()
    session_id = (data.get("session_id") or "default").strip() or "default"
    profile    = data.get("profile") if isinstance(data.get("profile"), dict) else {}
    jobs       = data.get("jobs") if isinstance(data.get("jobs"), list) else []
    lang       = (data.get("lang") or "en").lower()
    if not message:
        return jsonify({"ok": False, "error": "message required"}), 400
    if not config.OPENAI_API_KEY:
        return jsonify({"ok": False, "error": "OpenAI API key not configured"}), 503

    from jobs_intelligence_ai.core import send_candidate_message
    result = send_candidate_message(session_id, message, profile, jobs, lang)
    return jsonify({
        "ok":              True,
        "reply":           result.get("text") or "",
        "profile_updates": result.get("profile_updates") or {},
        "cv_note":         result.get("cv_note") or "",
    })


@bp.route("/assistant/reset", methods=["POST"])
def api_candidate_assistant_reset():
    """Body: { session_id } → clear the assistant's conversation memory."""
    data       = request.get_json(silent=True) or {}
    session_id = (data.get("session_id") or "default").strip() or "default"
    from jobs_intelligence_ai.core import clear_candidate_session
    clear_candidate_session(session_id)
    return jsonify({"ok": True})


@bp.route("/parse-profile", methods=["POST"])
def api_parse_profile():
    """
    Body: { text }
    Returns: { ok, name, title, experience_years, skills, location,
               languages, salary_expectation, availability, summary }
    """
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "No text provided"}), 400
    if not config.OPENAI_API_KEY:
        return jsonify({"ok": False, "error": "OpenAI API key not configured"}), 503

    try:
        from openai import OpenAI
        client = OpenAI(api_key=config.OPENAI_API_KEY)
        resp   = client.chat.completions.create(
            model=config.CLASSIFIER_MODEL,
            messages=[
                {"role": "system", "content": _PROFILE_SYSTEM},
                {"role": "user",   "content": text[:4000]},
            ],
            max_completion_tokens=400,
            temperature=0.1,
        )
        raw    = (resp.choices[0].message.content or "").strip()
        raw    = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
        result = _json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError("Expected JSON object")
        return jsonify({"ok": True, **result})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500
