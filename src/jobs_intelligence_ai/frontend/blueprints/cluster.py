"""
cluster.py — Multi-CV mode: cluster candidate profiles into talent segments.

Routes:
  POST /api/cluster   → embed N candidate profiles, cluster them into segments, and
                        synthesize a persona (synthetic candidate) per segment.

Phase 1 stops at the personas. Matching each segment to jobs reuses /api/match per
persona (driven from the front-end), so there's no new matching code here.
"""
import logging
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from flask import Blueprint, request, jsonify, session

from jobs_intelligence_ai import config
from jobs_intelligence_ai.services import clustering
from jobs_intelligence_ai.services.candidate import store as candidate_store
from jobs_intelligence_ai.services.search import utils as search_utils

bp = Blueprint("cluster", __name__, url_prefix="/api")
logger = logging.getLogger(__name__)


@bp.route("/cluster", methods=["POST"])
def api_cluster():
    """
    Body: { candidates: [{id?, name?, text}], granularity?: float 0..1 }
    Returns: { ok, count, clusters: [{cluster_id, title, summary, persona_text,
                                      size, members: [{index, id, name}]}] }
    """
    body = request.get_json(silent=True) or {}
    candidates = body.get("candidates") or []
    try:
        granularity = float(body.get("granularity", 0.5))
    except Exception:
        granularity = 0.5

    cand = [c for c in candidates if (c.get("text") or "").strip()]
    if len(cand) < 2:
        return jsonify({"ok": False, "error": "Add at least 2 candidate profiles to cluster."}), 400

    texts = [c["text"] for c in cand]
    try:
        vectors = clustering.embed_profiles(texts)
        labels  = clustering.cluster_labels(vectors, granularity)
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500

    # Group candidate indices by their segment label.
    groups: dict[int, list[int]] = {}
    for idx, lab in enumerate(labels):
        groups.setdefault(int(lab), []).append(idx)

    # Synthesize a persona per segment, concurrently (each is one LLM call).
    ordered = sorted(groups.items(), key=lambda kv: -len(kv[1]))   # biggest segments first
    with ThreadPoolExecutor(max_workers=min(8, len(ordered))) as ex:
        personas = list(ex.map(
            lambda kv: clustering.synthesize_persona([texts[i] for i in kv[1]]),
            ordered,
        ))

    clusters = []
    for (lab, idxs), p in zip(ordered, personas):
        members = [{"index": i,
                    "id":    cand[i].get("id"),
                    "name":  cand[i].get("name") or f"Candidate {i + 1}"}
                   for i in idxs]
        clusters.append({
            "cluster_id":   lab,
            "title":        p["title"],
            "summary":      p["summary"],
            "persona_text": p["persona_text"],
            "size":         len(idxs),
            "members":      members,
        })

    return jsonify({"ok": True, "count": len(clusters), "clusters": clusters})


@bp.route("/cluster/overview", methods=["POST"])
def api_cluster_overview():
    """
    Cross-segment opportunity analysis: an LLM looks across ALL segments — the
    candidates we have in each and the job openings that matched them — and reports
    where the most opportunity is.

    Body: { segments: [{title, summary, candidates, ab_jobs, total_jobs,
                        sample_jobs: [{title, grade}]}] }
    Returns: { ok, text }
    """
    body = request.get_json(silent=True) or {}
    segments = body.get("segments") or []
    if not segments:
        return jsonify({"ok": False, "error": "segments are required"}), 400

    lines = []
    for s in segments:
        samples = "; ".join(f"{j.get('title', '')} [{j.get('grade', '')}]"
                            for j in (s.get("sample_jobs") or [])[:6])
        lines.append(
            f"- Segment '{s.get('title', '')}': {s.get('candidates', 0)} candidate(s); "
            f"{s.get('ab_jobs', 0)} strong (A/B) roles of {s.get('total_jobs', 0)} matched. "
            f"Sample strong roles: {samples or 'none'}. {s.get('summary', '')}"
        )
    prompt = "TALENT SEGMENTS (candidates we have vs. open roles that matched them):\n" + "\n".join(lines)

    try:
        from jobs_intelligence_ai.core import get_client
        client = get_client()
        response = client.responses.create(
            model=config.CHAT_MODEL,
            instructions=(
                "You are a recruitment strategy analyst writing for an HR / recruitment lead. "
                "Each segment is a cluster of similar candidates, with how many candidates we have "
                "and how many strong (A/B grade) job openings matched that profile. Write a concise "
                "OPPORTUNITY OVERVIEW (~150–220 words) that: (1) ranks where the biggest opportunity "
                "is — segments with many strong open roles relative to the number of candidates "
                "(high demand, easy to place / worth sourcing more), (2) flags oversupplied segments "
                "(many candidates but few matching roles → competition / harder to place), and "
                "(3) gives 2–4 concrete recommendations on where to focus. Refer to segments by name "
                "and cite the role/candidate counts. Use short paragraphs or bullets. Respond in English."
            ),
            input=prompt,
        )
        return jsonify({"ok": True, "text": response.output_text or ""})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


def _sim_to_pct(cos: float) -> int:
    """Map a cosine similarity to a friendly 0–100 'similarity', so CV↔job scores
    (typically ~0.2–0.6) spread across a readable range. NOT an A/B/C fit grade."""
    return int(max(0.0, min(1.0, (cos - 0.15) / 0.50)) * 100)


@bp.route("/cluster/rank", methods=["POST"])
def api_cluster_rank():
    """
    Rank a segment's candidates against its jobs by embedding similarity (free — one
    batched embeddings call, no LLM grading).

    Body: { candidates: [{name, text}], jobs: [{job_id, title, text}] }
    Returns: { ok, candidate_ranking: [{name, score, pct}],
               job_fits: { job_id: [{name, score, pct}] } }
    """
    body       = request.get_json(silent=True) or {}
    candidates = [c for c in (body.get("candidates") or []) if (c.get("text") or "").strip()]
    jobs       = body.get("jobs") or []
    if not candidates or not jobs:
        return jsonify({"ok": False, "error": "candidates and jobs are required"}), 400

    cand_texts = [c["text"] for c in candidates]
    job_texts  = [(j.get("text") or j.get("title") or "") for j in jobs]
    try:
        vecs  = clustering.embed_profiles(cand_texts + job_texts)   # one batched call
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500
    cvecs = vecs[:len(cand_texts)]
    jvecs = vecs[len(cand_texts):]
    sims  = cvecs @ jvecs.T          # (C x J) cosine similarities (vectors are normalized)

    def _rank(scores):
        rows = [{"name": candidates[i]["name"], "score": round(float(scores[i]), 4),
                 "pct": _sim_to_pct(float(scores[i]))} for i in range(len(candidates))]
        rows.sort(key=lambda r: -r["score"])
        return rows

    candidate_ranking = _rank(sims.mean(axis=1))                    # avg fit across the jobs
    job_fits = {str(j.get("job_id")): _rank(sims[:, jdx]) for jdx, j in enumerate(jobs)}
    return jsonify({"ok": True, "candidate_ranking": candidate_ranking, "job_fits": job_fits})


@bp.route("/cluster/grade_job", methods=["POST"])
def api_cluster_grade_job():
    """
    Opt-in precise grading: score each candidate against ONE job with the LLM (one
    batched call). Costs credits — only called from the "Grade with AI" button.

    Body: { job: {title, company, skills|skills_en, description}, candidates: [{name, text}] }
    Returns: { ok, candidates: [{name, score, score_pct, grade, reason}] }
    """
    body       = request.get_json(silent=True) or {}
    job        = body.get("job") or {}
    candidates = [c for c in (body.get("candidates") or []) if (c.get("text") or "").strip()]
    if not job.get("title") or not candidates:
        return jsonify({"ok": False, "error": "job.title and candidates are required"}), 400

    job_desc = (f"Title: {job.get('title','')}\nCompany: {job.get('company','')}\n"
                f"Skills: {job.get('skills_en') or job.get('skills') or ''}\n"
                f"{(job.get('description') or '')[:900]}")
    lines = [f"{i}. {c.get('name','')}: {(c.get('text') or '')[:600]}"
             for i, c in enumerate(candidates)]
    prompt = "JOB:\n" + job_desc + "\n\nCANDIDATES:\n" + "\n".join(lines)
    try:
        from jobs_intelligence_ai.core import get_client
        client = get_client()
        resp = client.responses.create(
            model=config.CHAT_MODEL,
            instructions=(
                "Score how well EACH candidate fits THIS job. Respond with ONLY a JSON array, "
                "one object per candidate IN THE SAME ORDER, each: "
                '{"score": float 0.0-1.0, "reason": one short sentence}. '
                "Use the full range; judge genuine fit, not keyword overlap."
            ),
            input=prompt,
        )
        scores = search_utils.parse_json(resp.output_text or "")
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500

    out = []
    for i, c in enumerate(candidates):
        item = scores[i] if i < len(scores) and isinstance(scores[i], dict) else {}
        try:
            sc = round(max(0.0, min(1.0, float(item.get("score", 0.5)))), 3)
        except Exception:
            sc = 0.5
        out.append({"name": c.get("name", ""), "score": sc, "score_pct": f"{int(sc * 100)}%",
                    "grade": search_utils.grade(sc, config.SCORE_A_MIN, config.SCORE_B_MIN),
                    "reason": (item.get("reason") or "").strip()})
    out.sort(key=lambda r: -r["score"])
    return jsonify({"ok": True, "candidates": out})


@bp.route("/cluster/chat", methods=["POST"])
def api_cluster_chat():
    """
    Chat about one segment (explanations for the clustering, fit, etc.).
    Body: { session_id, message, segment: {title, summary, persona_text,
            members:[{name,text}], jobs:[{title,grade}]}, lang? }
    Returns: { ok, text }
    """
    body       = request.get_json(silent=True) or {}
    session_id = (body.get("session_id") or "").strip()
    message    = (body.get("message") or "").strip()
    segment    = body.get("segment") or {}
    lang       = body.get("lang", "en")
    if not message:
        return jsonify({"ok": False, "error": "message required"}), 400
    if not session_id:
        return jsonify({"ok": False, "error": "session_id required"}), 400
    try:
        from jobs_intelligence_ai.services.clustering import send_segment_message
        return jsonify({"ok": True, **send_segment_message(session_id, message, segment, lang=lang)})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


def _candidate_to_text(c: dict) -> str:
    """Flatten a saved-candidate summary row into a profile text for clustering."""
    parts = [c.get("name") or ""]
    for label, key in (("Title", "title"), ("Seniority", "seniority"),
                       ("Experience", "experience"), ("Skills", "skills"),
                       ("Languages", "languages"), ("Location", "location")):
        if c.get(key):
            parts.append(f"{label}: {c[key]}")
    blurb = c.get("summary") or c.get("aiSummary")
    if blurb:
        parts.append(blurb)
    return "\n".join(parts)


@bp.route("/cluster/candidates", methods=["GET"])
def api_cluster_candidates():
    """List saved candidates (with a profile) as a pickable pool for clustering.
    Returns: { ok, candidates: [{name, title, text, isTemplate}] }"""
    try:
        rows = candidate_store.list_candidates_detailed()
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500
    out = [{"name": r["name"], "title": r.get("title", ""),
            "isTemplate": r.get("isTemplate", False), "text": _candidate_to_text(r)}
           for r in rows if r.get("hasProfile")]
    return jsonify({"ok": True, "candidates": out})


@bp.route("/cluster/save_persona", methods=["POST"])
def api_save_persona():
    """Persist a segment's persona as a synthetic (template) candidate, reusable and
    re-matchable like any saved candidate.

    Body: { title, persona_text, members?: [name, ...] }
    Returns: { ok, name }
    """
    body         = request.get_json(silent=True) or {}
    title        = (body.get("title") or "Candidate segment").strip()
    persona_text = (body.get("persona_text") or "").strip()
    members      = [m for m in (body.get("members") or []) if m]
    if not persona_text:
        return jsonify({"ok": False, "error": "persona_text is required"}), 400

    name = f"◇ {title}"   # marker distinguishes synthetic personas from real people
    note = f"\n\n[Synthetic persona from {len(members)} candidate(s)"
    note += (": " + ", ".join(members) + "]") if members else "]"
    profile = {"title": title, "summary": persona_text + note, "source": "template"}
    try:
        candidate_store.upsert_profile(name, profile, created_by=session.get("username"))
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500
    return jsonify({"ok": True, "name": name})
