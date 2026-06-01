"""
tabs/search.py — Search tab (CV matching).

Routes:
  GET  /api/filters       → filter dropdown options
  POST /api/match         → run AI/vector matching against a candidate profile
  POST /api/quality       → score a batch of jobs for quality
"""
from flask import Blueprint, request, jsonify
import config
from core.database import get_filter_options
from core.matching import run_matching

bp = Blueprint("search", __name__, url_prefix="/api")


@bp.route("/filters")
def api_filters():
    try:
        options = get_filter_options()
        return jsonify({"ok": True, "data": options})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/match", methods=["POST"])
def api_match():
    """
    Body: { candidate_text, filters?, top_n? }
    Returns ranked job list with score, grade, match_reason.
    """
    body           = request.get_json(silent=True) or {}
    candidate_text = body.get("candidate_text", "").strip()
    filters        = body.get("filters", {})
    top_n          = int(body.get("top_n", config.DEFAULT_TOP_N))

    if not candidate_text:
        return jsonify({"ok": False, "error": "candidate_text is required"}), 400

    try:
        results = run_matching(candidate_text, filters, top_n)
        return jsonify({"ok": True, "count": len(results), "top_n": top_n, "jobs": results})
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
        from stats.salary_stats import get_group_stats
        from helpers.quality_classifier import classify_quality
        group_stats = get_group_stats(occ_group, state) if occ_group else {}
        result_jobs = classify_quality(list(jobs), group_stats)
        return jsonify({"ok": True, "jobs": result_jobs, "group_stats": group_stats})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500
