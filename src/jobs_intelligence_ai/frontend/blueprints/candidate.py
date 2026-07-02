"""
tabs/candidate.py — Candidate CV management.

Routes:
  GET  /api/candidate/example-pdf    → download Anna Bauer example CV PDF (AT)
  GET  /api/candidate/example-pdf-2  → download Max Weber example CV PDF (AT)
  GET  /api/candidate/example-pdf-sk → download Marek Novák example CV PDF (SK)
  POST /api/candidate/parse-pdf      → extract text from an uploaded PDF
  POST /api/candidate/parse-profile  → parse structured profile from raw text using AI
"""
from flask import Blueprint, request, jsonify, Response
from jobs_intelligence_ai import config

bp = Blueprint("candidate", __name__, url_prefix="/api/candidate")


@bp.route("/example-pdf", methods=["GET"])
def api_example_cv():
    from jobs_intelligence_ai.services.candidate import generate_example_cv_pdf
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
    from jobs_intelligence_ai.services.candidate import generate_example_cv_pdf_2
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
    from jobs_intelligence_ai.services.candidate import generate_example_cv_pdf_sk
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

    from jobs_intelligence_ai.infra.integrations.linkedin import (
        enrich_linkedin, map_to_profile, to_candidate_text, error_message)
    from jobs_intelligence_ai.services.candidate import enrich_linkedin_profile
    try:
        items = enrich_linkedin(urls)
        # The scraper returns one item per URL; failed ones (deleted / private /
        # not-found profile) carry an error and map to a nameless profile. Build
        # only the ones that mapped to a real candidate — `requested` vs `count`
        # shows the gap — so failures don't become blank cards.
        profiles = []
        for it in (items or []):
            # Mechanical map = accurate structured base; AI then analyzes it and
            # layers on inferred fields (seniority, salary, summary, …).
            base = map_to_profile(it)
            if not base.get("name"):
                continue
            prof = enrich_linkedin_profile(it, base=base)
            profiles.append({"profile": prof, "text": to_candidate_text(base)})
        if not profiles:
            msg = next((error_message(it) for it in (items or []) if error_message(it)), None) \
                  or "No data returned for those profiles"
            return jsonify({"ok": False, "error": msg}), 404
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

    from jobs_intelligence_ai.services.candidate import parse_candidate_profile
    try:
        result = parse_candidate_profile(text)
        return jsonify({"ok": True, **result})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500
