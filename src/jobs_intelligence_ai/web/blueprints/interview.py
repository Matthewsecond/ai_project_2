"""
web/blueprints/interview.py — Live interview scoring in the job-detail modal.

Thin wrappers over services.interview_helper.InterviewHelper. The interview
RECORD (questions + recorded answers + scores) is persisted by the front-end into
the saved job's `extras.interview` via the existing /api/saved routes — these
endpoints are stateless and just do the AI work.

Routes:
  POST /api/interview/questions   → gap-based questions for (job, cv)
  POST /api/interview/extract     → plain text from an uploaded .docx/.pdf/.txt
  POST /api/interview/parse       → import a prepared doc into Q/A pairs
  POST /api/interview/analyze     → score one recorded answer
  POST /api/interview/context     → assembled briefing note (what the model sees)
  POST /api/interview/followup    → suggest one follow-up (or report exhausted)
  POST /api/interview/summarize   → overall read across answered questions
  POST /api/interview/model_answer→ candidate coaching: what a strong answer covers
  POST /api/interview/opportunities→ candidate's ranked ways to improve their chances

Note: distinct from /api/saved/observation (formerly /api/saved/interview), which is
an unrelated feature (HR observation → candidate-profile override).
"""
import traceback
from flask import Blueprint, request, jsonify

from jobs_intelligence_ai.services.interview_helper import InterviewHelper

bp = Blueprint("interview", __name__, url_prefix="/api/interview")

_helper = InterviewHelper()


def _fail(e: Exception):
    return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


@bp.route("/questions", methods=["POST"])
def api_interview_questions():
    """Body: { job: dict, cv_text, profile?, lang? }  →  { ok, questions:[{id,question,note}] }"""
    body = request.get_json(silent=True) or {}
    job = body.get("job") or {}
    cv_text = (body.get("cv_text") or "").strip()
    lang = body.get("lang", "en")
    try:
        result = _helper.generate_questions(job, cv_text, lang=lang,
                                            profile=body.get("profile") or None)
        return jsonify(result), (200 if result.get("ok") else 400)
    except Exception as e:
        return _fail(e)


def _extract_docx(stream) -> str:
    """Plain text from a .docx, paragraph per line — no extra dependency (a .docx
    is a zip; the body lives in word/document.xml as <w:t> runs inside <w:p>)."""
    import zipfile, re, html
    with zipfile.ZipFile(stream) as z:
        xml = z.read("word/document.xml").decode("utf-8", "ignore")
    paras = re.split(r"</w:p>", xml)
    lines = ["".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", p, re.DOTALL)) for p in paras]
    return "\n".join(html.unescape(ln).strip() for ln in lines if ln.strip())


@bp.route("/extract", methods=["POST"])
def api_interview_extract():
    """Multipart file upload (.docx / .pdf / .txt / .md) → { ok, text }.

    Pulls plain text out of a prepared interview document so it can be reviewed in
    the import box and then parsed into Q/A pairs. Parsing stays a separate step so
    the recruiter can edit the extracted text first."""
    f = request.files.get("file")
    if not f:
        return jsonify({"ok": False, "error": "No file uploaded"}), 400
    name = (f.filename or "").lower()
    try:
        if name.endswith(".docx"):
            text = _extract_docx(f.stream)
        elif name.endswith(".pdf"):
            from pypdf import PdfReader
            reader = PdfReader(f.stream)
            text = "\n\n".join(t.strip() for page in reader.pages if (t := page.extract_text()))
        else:  # .txt / .md / anything else: treat as UTF-8 text
            text = f.stream.read().decode("utf-8", "ignore")
        return jsonify({"ok": True, "text": (text or "")[:12000]})
    except Exception as e:
        return _fail(e)


@bp.route("/parse", methods=["POST"])
def api_interview_parse():
    """Body: { text }  →  { ok, questions:[{id,question,answer}] }

    Parse a prepared free-form interview document (questions, and answers if the
    recruiter has them) into ordered Q/A pairs for import into the scorecard."""
    body = request.get_json(silent=True) or {}
    try:
        result = _helper.parse_questions((body.get("text") or "").strip())
        return jsonify(result), (200 if result.get("ok") else 400)
    except Exception as e:
        return _fail(e)


@bp.route("/analyze", methods=["POST"])
def api_interview_analyze():
    """Body: { question, answer, note?, job, cv_text?, profile?, others?, lang?, final? }
    Returns: { ok, complete, status, needs, score, verdict, strengths, concerns, signals }

    The model judges whether the exchange is a complete answer or still in progress
    (clarifying/partial) and only scores when complete; `final=true` forces a score."""
    body = request.get_json(silent=True) or {}
    try:
        result = _helper.analyze_answer(
            question=(body.get("question") or "").strip(),
            answer=(body.get("answer") or "").strip(),
            job=body.get("job") or {},
            cv_text=(body.get("cv_text") or "").strip(),
            lang=body.get("lang", "en"),
            note=(body.get("note") or "").strip(),
            profile=body.get("profile") or None,
            others=body.get("others") or None,
            final=bool(body.get("final")),
        )
        return jsonify(result), (200 if result.get("ok") else 400)
    except Exception as e:
        return _fail(e)


@bp.route("/context", methods=["POST"])
def api_interview_context():
    """Body: { job, cv_text?, profile?, others? }  →  { ok, context }

    The assembled briefing note (job + candidate + interview-so-far) exactly as sent
    to the model — powers the "🔍 AI context" panel so it's visible, not just internal."""
    body = request.get_json(silent=True) or {}
    try:
        ctx = _helper.preview_context(
            job=body.get("job") or {},
            cv_text=(body.get("cv_text") or "").strip(),
            profile=body.get("profile") or None,
            others=body.get("others") or None,
        )
        return jsonify({"ok": True, "context": ctx})
    except Exception as e:
        return _fail(e)


@bp.route("/followup", methods=["POST"])
def api_interview_followup():
    """Body: { thread:[{question,answer,note?}], job, cv_text?, profile?, lang? }
    Returns: { ok, exhausted, question, note, reason }

    Propose ONE next follow-up for a single line of questioning, or report the
    thread is exhausted (so the interview doesn't generate questions endlessly)."""
    body = request.get_json(silent=True) or {}
    try:
        result = _helper.suggest_followup(
            thread=body.get("thread") or [],
            job=body.get("job") or {},
            cv_text=(body.get("cv_text") or "").strip(),
            lang=body.get("lang", "en"),
            profile=body.get("profile") or None,
            others=body.get("others") or None,
        )
        return jsonify(result), (200 if result.get("ok") else 400)
    except Exception as e:
        return _fail(e)


@bp.route("/summarize", methods=["POST"])
def api_interview_summarize():
    """Body: { records:[{question,answer,score,verdict,...}], job, cv_text?, profile?, lang? }
    Returns: { ok, score, recommendation, summary }"""
    body = request.get_json(silent=True) or {}
    try:
        result = _helper.summarize(
            records=body.get("records") or [],
            job=body.get("job") or {},
            cv_text=(body.get("cv_text") or "").strip(),
            lang=body.get("lang", "en"),
            profile=body.get("profile") or None,
        )
        return jsonify(result), (200 if result.get("ok") else 400)
    except Exception as e:
        return _fail(e)


@bp.route("/model_answer", methods=["POST"])
def api_interview_model_answer():
    """Body: { question, job, cv_text?, note?, profile?, lang? }
    Returns: { ok, model_answer, covers:[<point>] }

    Candidate coaching — what a strong answer to this question covers for the role.
    Revealed only after the candidate has answered (the front-end gates it)."""
    body = request.get_json(silent=True) or {}
    try:
        result = _helper.model_answer(
            question=(body.get("question") or "").strip(),
            job=body.get("job") or {},
            cv_text=(body.get("cv_text") or "").strip(),
            lang=body.get("lang", "en"),
            note=(body.get("note") or "").strip(),
            profile=body.get("profile") or None,
        )
        return jsonify(result), (200 if result.get("ok") else 400)
    except Exception as e:
        return _fail(e)


@bp.route("/opportunities", methods=["POST"])
def api_interview_opportunities():
    """Body: { records:[{question, answer, score?, ...}], job, cv_text?, profile?, lang? }
    Returns: { ok, opportunities:[{title, rationale, action, impact}], summary }

    Candidate-facing re-read of CV + answers: the biggest ranked opportunities to
    improve their chances for the role, each with a concrete how-to."""
    body = request.get_json(silent=True) or {}
    try:
        result = _helper.improvement_opportunities(
            records=body.get("records") or [],
            job=body.get("job") or {},
            cv_text=(body.get("cv_text") or "").strip(),
            lang=body.get("lang", "en"),
            profile=body.get("profile") or None,
        )
        return jsonify(result), (200 if result.get("ok") else 400)
    except Exception as e:
        return _fail(e)


@bp.route("/assess", methods=["POST"])
def api_interview_assess():
    """Body: { job, cv_text?, profile?, records?, prior_aspects?, lang? }
    Returns: { ok, aspects:[{aspect,score,status,note}], summary }

    The helper's running candidate read across key aspects — call after each
    recorded answer to refresh it. `prior_aspects` keeps aspect names stable."""
    body = request.get_json(silent=True) or {}
    try:
        result = _helper.assess_candidate(
            job=body.get("job") or {},
            cv_text=(body.get("cv_text") or "").strip(),
            profile=body.get("profile") or None,
            records=body.get("records") or [],
            lang=body.get("lang", "en"),
            prior_aspects=body.get("prior_aspects") or None,
        )
        return jsonify(result), (200 if result.get("ok") else 400)
    except Exception as e:
        return _fail(e)
