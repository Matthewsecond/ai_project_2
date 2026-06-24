"""
tabs/search.py — Search tab (CV matching).

Routes:
  GET  /api/filters       → filter dropdown options
  POST /api/match         → run AI/vector matching against a candidate profile
  POST /api/match/url     → grade ONE job (looked up by posting URL) for a candidate
  POST /api/match/analyze → overall analysis of the candidate vs the matched jobs
  POST /api/quality       → score a batch of jobs for quality
"""
import json
from flask import Blueprint, request, jsonify, Response, stream_with_context
from jobs_intelligence_ai.infra.database import get_filter_options
from jobs_intelligence_ai.core import Orchestrator, Rescorer, Highlighter, analyze_candidate_match

bp = Blueprint("search", __name__, url_prefix="/api")

# One shared instance each — the orchestrator lazily creates and reuses a single
# OpenAI client across requests.
_orchestrator = Orchestrator()
_rescorer     = Rescorer()
_highlighter  = Highlighter()


@bp.route("/filters")
def api_filters():
    try:
        options = get_filter_options()
        return jsonify({"ok": True, "data": options})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def _filters_from(body: dict) -> dict:
    """Build the filters dict from the request body.

    Result count is unlimited by default; the UI's optional top_n is folded in as
    a `limit` filter (the convergence set is small, so showing all is sensible).
    """
    filters = dict(body.get("filters") or {})
    limit = body.get("top_n")
    if limit:
        filters["limit"] = int(limit)
    return filters


def _max_results_from(body: dict) -> int | None:
    """Optional Stage-1 retrieval-breadth override (capped at the API's 50). Used by
    'find more jobs' to pull a wider candidate set than the default search."""
    n = body.get("max_results")
    return min(int(n), 50) if n else None


@bp.route("/match", methods=["POST"])
def api_match():
    """
    Body: { candidate_text, filters?, top_n?, max_results? }
    Returns ranked job list with score, grade, match_reason. max_results widens
    Stage-1 retrieval (used by "find more jobs").
    """
    body           = request.get_json(silent=True) or {}
    candidate_text = body.get("candidate_text", "").strip()

    if not candidate_text:
        return jsonify({"ok": False, "error": "candidate_text is required"}), 400

    try:
        results = _orchestrator.run(candidate_text, _filters_from(body),
                                    max_results=_max_results_from(body))
        return jsonify({"ok": True, "count": len(results), "jobs": results})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


@bp.route("/match/url", methods=["POST"])
def api_match_url():
    """
    Match a candidate against ONE job identified by its posting URL.

    Body: { candidate_text, url }
    Returns:
      { ok: true, in_db: true,  job: {...graded...} }   ← url found in DB + graded
      { ok: true, in_db: false, message }               ← url not in DB (scrape later)

    Only URLs already in the database are supported for now; live scraping of an
    unknown URL is a planned follow-up.
    """
    body           = request.get_json(silent=True) or {}
    candidate_text = (body.get("candidate_text") or "").strip()
    url            = (body.get("url") or "").strip()

    if not candidate_text:
        return jsonify({"ok": False, "error": "candidate_text is required"}), 400
    if not url:
        return jsonify({"ok": False, "error": "url is required"}), 400

    try:
        job = _orchestrator.match_url(candidate_text, url)
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500

    if job is None:
        return jsonify({"ok": True, "in_db": False,
                        "message": "This URL isn't in the database yet. "
                                   "Live scraping of new postings is coming soon."})
    return jsonify({"ok": True, "in_db": True, "job": job})


@bp.route("/match/stream", methods=["POST"])
def api_match_stream():
    """
    Streaming variant of /api/match (Server-Sent Events).

    Body: { candidate_text, filters?, top_n? }
    Emits one SSE `data:` line per event:
      {"event":"cycle","cycle":k,"added":a,"total":t}   ← retrieval progress
      {"event":"done","jobs":[...],"cycles":k,"total":t} ← final ranked set
      {"event":"error","error":"..."}                    ← on failure
    The front-end shows a "Searching…" meter from the cycle event(s) and renders
    the table from the done event; it falls back to /api/match if streaming fails.
    """
    body           = request.get_json(silent=True) or {}
    candidate_text = (body.get("candidate_text") or "").strip()
    filters        = _filters_from(body)

    if not candidate_text:
        return jsonify({"ok": False, "error": "candidate_text is required"}), 400

    max_results = _max_results_from(body)

    @stream_with_context
    def generate():
        try:
            for event in _orchestrator.stream(candidate_text, filters, max_results):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            import traceback
            logger_payload = {"event": "error", "error": str(e),
                              "trace": traceback.format_exc()}
            yield f"data: {json.dumps(logger_payload)}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache",
                             "X-Accel-Buffering": "no"})


@bp.route("/match/rescore", methods=["POST"])
def api_match_rescore():
    """
    Re-score a FROZEN set of jobs against an (updated) candidate profile.

    Body: { candidate_text, jobs: [{job_id, title, company, city, state,
                                     skills|skills_en, summary|description}] }
    Returns: { ok, jobs: [{job_id, score, score_pct, grade, match_reason}] }
    The job set is unchanged — only scores/reasons are recomputed, so the front-end
    can keep the same rows and animate the re-ranking.
    """
    body           = request.get_json(silent=True) or {}
    candidate_text = (body.get("candidate_text") or "").strip()
    jobs           = body.get("jobs") or []

    if not candidate_text:
        return jsonify({"ok": False, "error": "candidate_text is required"}), 400
    if not jobs:
        return jsonify({"ok": False, "error": "jobs array required"}), 400

    try:
        scored = _rescorer.rescore(candidate_text, jobs)
        return jsonify({"ok": True, "count": len(scored), "jobs": scored})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


@bp.route("/match/highlight", methods=["POST"])
def api_match_highlight():
    """
    Decide which of the given jobs match a natural-language CRITERION, so the UI
    can highlight them (e.g. "roles with travel benefits").

    Body: { criterion, jobs: [{job_id, title, company, salary, skills|skills_en,
                               summary|description, city, state}] }
    Returns: { ok, job_ids: [...], count }
    """
    body      = request.get_json(silent=True) or {}
    criterion = (body.get("criterion") or "").strip()
    jobs      = body.get("jobs") or []

    if not criterion:
        return jsonify({"ok": False, "error": "criterion is required"}), 400
    if not jobs:
        return jsonify({"ok": False, "error": "jobs array required"}), 400

    try:
        ids = _highlighter.highlight(criterion, jobs)
        return jsonify({"ok": True, "job_ids": ids, "count": len(ids)})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


@bp.route("/match/analyze", methods=["POST"])
def api_match_analyze():
    """
    Overall analysis of how the candidate stacks up against the CURRENT matched jobs —
    strengths, recurring skill/experience gaps, and what they could work on.

    Body: { candidate_text, jobs: [{title, company, grade, score_pct, skills|skills_en,
                                    summary|description, city, state}] }
    Returns: { ok, text }
    """
    body           = request.get_json(silent=True) or {}
    candidate_text = (body.get("candidate_text") or "").strip()
    jobs           = body.get("jobs") or []

    if not candidate_text:
        return jsonify({"ok": False, "error": "candidate_text is required"}), 400
    if not jobs:
        return jsonify({"ok": False, "error": "jobs array required"}), 400

    try:
        return jsonify({"ok": True, "text": analyze_candidate_match(candidate_text, jobs)})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


@bp.route("/quality", methods=["POST"])
def api_quality():
    """
    Body: { jobs: [...], occ_group: str, state?: str }
    Returns jobs enriched with quality fields.
    """
    body      = request.get_json(silent=True) or {}
    jobs      = body.get("jobs") or []
    occ_group = body.get("occ_group") or ""
    state     = body.get("state") or None

    if not jobs:
        return jsonify({"ok": False, "error": "jobs array required"}), 400

    try:
        from jobs_intelligence_ai.services.stats import get_group_stats
        from jobs_intelligence_ai.services.enrichment import classify_quality
        group_stats = get_group_stats(occ_group, state) if occ_group else {}
        result_jobs = classify_quality(list(jobs), group_stats)
        return jsonify({"ok": True, "jobs": result_jobs, "group_stats": group_stats})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500
