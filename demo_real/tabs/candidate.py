"""
tabs/candidate.py — Candidate CV management.

Routes:
  GET  /api/candidate/example-pdf    → download Anna Bauer example CV PDF
  GET  /api/candidate/example-pdf-2  → download Max Weber example CV PDF
  POST /api/candidate/parse-pdf      → extract text from an uploaded PDF
  POST /api/candidate/parse-profile  → parse structured profile from raw text using AI
"""
import re
import json as _json
from flask import Blueprint, request, jsonify, Response
import config

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
  "summary": "One concise sentence describing this candidate's profile"
}
"""


@bp.route("/example-pdf", methods=["GET"])
def api_example_cv():
    from helpers.example_cv import generate_example_cv_pdf
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
    from helpers.example_cv import generate_example_cv_pdf_2
    pdf_bytes = generate_example_cv_pdf_2()
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="Max_Weber_CV.pdf"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )


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
