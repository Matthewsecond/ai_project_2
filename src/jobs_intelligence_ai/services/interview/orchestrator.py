"""
orchestrator.py — Live interview scoring for the job-detail modal.

`InterviewHelper` owns the whole interview loop for one (candidate, job) pair:

    generate_questions(job, cv_text)  → gap-based questions to ask
    analyze_answer(question, answer)  → score + qualitative read of one answer
    summarize(records)                → overall recommendation across answers

It is deliberately a small class rather than a few inline endpoint functions so the
evaluation RUBRIC (how an answer is judged) lives in one place — see `config.py`, which
holds the rubric, calibration, per-call prompts and the Structured-Outputs schemas. The
recruiter records what the candidate said against each question; each answer is scored
0–100 and tagged with strengths, concerns, and soft signals that aren't on the nose.

All AI calls go through the shared OpenAI client (`shared.llm.get_client`) and use
`config.CHAT_MODEL`. Each call uses Structured Outputs (`responses.parse(text_format=…)`),
so replies are schema-validated rather than parsed out of prose. Every method degrades to
a structured error dict instead of raising, so a flaky model call never 500s the UI.
"""
import json
import logging

from jobs_intelligence_ai import config
from jobs_intelligence_ai.shared.llm import get_client
from . import config as ic   # interview config: prompts + Structured-Outputs schemas

logger = logging.getLogger(__name__)


class InterviewHelper:
    """Stateless helper — one instance is reused across requests; the interview
    record itself is held by the caller (front-end / saved-job extras)."""

    def __init__(self, client=None, model: str | None = None):
        self._client = client
        self._model = model or ic.MODEL

    # ── client / low-level call ────────────────────────────────────────────────
    @property
    def client(self):
        if self._client is None:
            self._client = get_client()
        return self._client

    def _call_parsed(self, instructions: str, prompt: str, schema):
        """One Structured-Outputs model call. Returns the validated `output_parsed`
        Pydantic object, or a {"_error": ...} dict so callers can surface failure
        without raising."""
        if not config.OPENAI_API_KEY:
            return {"_error": "Interview features require an OpenAI API key — add OPENAI_API_KEY to your .env file."}
        try:
            resp = self.client.responses.parse(
                model=self._model, instructions=instructions, input=prompt,
                text_format=schema)
            parsed = resp.output_parsed
            if parsed is None:
                return {"_error": "model returned no structured output"}
            return parsed
        except Exception as e:
            logger.error("InterviewHelper call failed: %s", e)
            return {"_error": str(e)}

    @staticmethod
    def _err(data):
        """The error string if `data` is a {"_error": ...} dict, else None."""
        if isinstance(data, dict) and "_error" in data:
            return data["_error"]
        return None

    # ── job / cv context block shared by every prompt ──────────────────────────
    @staticmethod
    def _context(job: dict, cv_text: str, profile: dict | None = None) -> str:
        # Salary and location matter for calibrating expectations and follow-ups, so
        # surface them when the caller sends them (optional lines).
        salary = job.get("salary") or job.get("salary_range")
        location = job.get("location") or ", ".join(
            x for x in (job.get("city"), job.get("state")) if x)
        block = (
            f"JOB TITLE: {job.get('title', '—')}\n"
            f"COMPANY: {job.get('company', '—')}\n"
            + (f"SALARY: {salary}\n" if salary else "")
            + (f"LOCATION: {location}\n" if location else "")
            + f"REQUIRED SKILLS: {job.get('skills_en') or job.get('skills') or 'not specified'}\n"
            f"JOB DESCRIPTION:\n{(job.get('description') or job.get('description_snippet') or '')[:2500]}\n\n"
            f"CANDIDATE CV:\n{(cv_text or '')[:2500]}"
        )
        # The recruiter's already-computed read of the candidate (structured profile
        # + AI summary). Lets the helper build on prior analysis instead of working
        # from the raw CV alone.
        prof = _profile_text(profile)
        if prof:
            block += f"\n\nCANDIDATE PROFILE / PRIOR ANALYSIS:\n{prof}"
        return block

    # ── 1. questions ───────────────────────────────────────────────────────────
    def generate_questions(self, job: dict, cv_text: str, lang: str = "en",
                           n: int = 6, profile: dict | None = None) -> dict:
        """Return {"ok", "questions":[{id, question, note}]} — gap-based interview
        questions, structured so each can carry its own answer + score."""
        if not (job.get("title") and (cv_text or "").strip()):
            return {"ok": False, "error": "job.title and cv_text required"}
        lang_note = ic.LANG_NOTE.get(lang, ic.LANG_NOTE["en"])
        instructions = ic.QUESTIONS_PROMPT.format(n=n) + lang_note
        data = self._call_parsed(instructions, self._context(job, cv_text, profile),
                                 ic.QuestionList)
        if (err := self._err(data)):
            return {"ok": False, "error": err}
        questions = _coerce_questions(data.model_dump()["questions"])
        if not questions:
            return {"ok": False, "error": "model returned no questions"}
        return {"ok": True, "questions": questions}

    # ── 1b. import / parse a prepared document ─────────────────────────────────
    def parse_questions(self, text: str) -> dict:
        """Parse a prepared free-form interview document into structured pairs.

        The recruiter may already have questions (and sometimes the candidate's
        answers) in a Word/text file where Q and A simply alternate with NO labels
        and not every question has an answer. Returns
        {"ok", "questions":[{id, question, answer}]} — answer is "" when absent.
        Wording/language is preserved verbatim (no translation or summarising)."""
        text = (text or "").strip()
        if not text:
            return {"ok": False, "error": "no text to parse"}
        data = self._call_parsed(ic.PARSE_PROMPT, text[:12000], ic.ParsedQAList)
        if (err := self._err(data)):
            return {"ok": False, "error": err}
        questions = _coerce_parsed(data.model_dump()["questions"])
        if not questions:
            return {"ok": False, "error": "no questions found in the text"}
        return {"ok": True, "questions": questions}

    # ── 2. analyze one answer ──────────────────────────────────────────────────
    def analyze_answer(self, question: str, answer: str, job: dict, cv_text: str,
                       lang: str = "en", note: str = "", profile: dict | None = None,
                       others: list[dict] | None = None, final: bool = False) -> dict:
        """Assess one turn of a LIVE interview. The model first judges whether the
        exchange is a COMPLETE answer or still in progress (a clarifying/scoping
        question or a partial answer), and only commits a score when it's complete —
        so the tool doesn't jump to a verdict mid-conversation. A clarifying question
        is treated as a legitimate, often positive move, never an auto-fail.

        `final=True` is the interviewer override ("Score it now"): score the exchange
        as it stands even if the model would otherwise keep it open.

        Returns {"ok", "complete", "status"(answer|clarifying|partial), "needs",
        "score"(null when not complete), "verdict", "strengths", "concerns", "signals"}."""
        if not (question or "").strip() or not (answer or "").strip():
            return {"ok": False, "error": "question and answer required"}
        lang_note = ic.LANG_NOTE.get(lang, ic.LANG_NOTE["en"])
        gate = ic.ANALYZE_GATE + (ic.ANALYZE_FINAL_NOTE if final else ic.ANALYZE_OPEN_NOTE)
        instructions = gate + ic.ANALYZE_SCORING + lang_note
        gap = f"\nGAP THIS QUESTION PROBES: {note}" if note else ""
        prompt = (
            f"{self._context(job, cv_text, profile)}{_others_block(others)}\n\n"
            f"INTERVIEW QUESTION: {question}{gap}\n\n"
            f"THE EXCHANGE SO FAR (interviewer's notes — may be multiple turns):\n{answer[:2000]}"
        )
        data = self._call_parsed(instructions, prompt, ic.AnswerAnalysis)
        if (err := self._err(data)):
            return {"ok": False, "error": err}
        return {"ok": True, **_coerce_analysis(data.model_dump(), force_complete=final)}

    # ── context preview (for the "what the AI sees" panel) ─────────────────────
    def preview_context(self, job: dict, cv_text: str, profile: dict | None = None,
                        others: list[dict] | None = None) -> str:
        """The assembled briefing note exactly as sent to the model (job + candidate +
        interview-so-far), minus the per-call instructions/question. Lets the UI show
        the recruiter what context the AI is working with."""
        return self._context(job, cv_text, profile) + _others_block(others)

    # ── 2b. suggest one follow-up (or stop) ─────────────────────────────────────
    def suggest_followup(self, thread: list[dict], job: dict, cv_text: str,
                         lang: str = "en", profile: dict | None = None,
                         others: list[dict] | None = None) -> dict:
        """Propose ONE next follow-up for a single line of questioning — or report
        the thread is exhausted so the interview doesn't generate questions forever.

        `thread` = [{question, answer, note?}] in order: the original question and
        its answer first, then each follow-up already asked in this thread with its
        answer. Returns {"ok", "exhausted", "question", "note", "reason"}."""
        thread = [t for t in (thread or []) if (t.get("question") or "").strip()]
        if not thread:
            return {"ok": False, "error": "thread with at least one question+answer required"}
        if not any((t.get("answer") or "").strip() for t in thread):
            return {"ok": False, "error": "no answer to follow up on yet"}
        lang_note = ic.LANG_NOTE.get(lang, ic.LANG_NOTE["en"])
        instructions = ic.FOLLOWUP_PROMPT + lang_note
        lines = []
        for i, t in enumerate(thread, 1):
            label = "ORIGINAL QUESTION" if i == 1 else f"FOLLOW-UP {i - 1}"
            lines.append(
                f"{label}: {t.get('question', '')}\n"
                f"  Answer: {(t.get('answer') or '(not answered yet)')[:800]}"
            )
        prompt = (self._context(job, cv_text, profile)
                  + _others_block(others)
                  + "\n\nLINE OF QUESTIONING SO FAR:\n" + "\n\n".join(lines))
        data = self._call_parsed(instructions, prompt, ic.Followup)
        if (err := self._err(data)):
            return {"ok": False, "error": err}
        return {"ok": True, **_coerce_followup(data.model_dump())}

    # ── 3. summarize the interview ─────────────────────────────────────────────
    def summarize(self, records: list[dict], job: dict, cv_text: str,
                  lang: str = "en", profile: dict | None = None) -> dict:
        """Aggregate answered questions into an overall read.

        `records` = [{question, answer, score, verdict, strengths, concerns,
        signals}]. Returns {"ok", "score", "recommendation", "summary"}."""
        answered = [r for r in (records or []) if (r.get("answer") or "").strip()]
        if not answered:
            return {"ok": False, "error": "no answered questions to summarize"}
        lang_note = ic.LANG_NOTE.get(lang, ic.LANG_NOTE["en"])
        lines = []
        for i, r in enumerate(answered, 1):
            lines.append(
                f"Q{i}: {r.get('question', '')}\n"
                f"  Answer: {(r.get('answer') or '')[:600]}\n"
                f"  Score: {r.get('score', '—')}  Verdict: {r.get('verdict', '')}"
            )
        instructions = ic.SUMMARIZE_PROMPT + lang_note
        prompt = self._context(job, cv_text, profile) + "\n\nSCORED ANSWERS:\n" + "\n\n".join(lines)
        data = self._call_parsed(instructions, prompt, ic.InterviewSummary)
        if (err := self._err(data)):
            return {"ok": False, "error": err}
        d = data.model_dump()
        return {
            "ok": True,
            "score": _clamp_score(d.get("score")),
            "recommendation": str(d.get("recommendation") or "").strip(),
            "summary": str(d.get("summary") or "").strip(),
        }

    # ── 3b. model answer (candidate coaching, revealed after they answer) ───────
    def model_answer(self, question: str, job: dict, cv_text: str, lang: str = "en",
                     note: str = "", profile: dict | None = None) -> dict:
        """Coaching for the CANDIDATE: what a STRONG answer to this question covers
        for THIS role — the points, evidence and framing the company is really after.

        Meant to be revealed only AFTER the candidate has answered, so it guides
        without handing them a script to recite. Returns
        {"ok", "model_answer", "covers":[<key point>]}."""
        if not (question or "").strip():
            return {"ok": False, "error": "question required"}
        lang_note = ic.LANG_NOTE.get(lang, ic.LANG_NOTE["en"])
        instructions = ic.MODEL_ANSWER_PROMPT + lang_note
        gap = f"\nGAP THIS QUESTION PROBES: {note}" if note else ""
        prompt = (self._context(job, cv_text, profile)
                  + f"\n\nINTERVIEW QUESTION: {question}{gap}")
        data = self._call_parsed(instructions, prompt, ic.ModelAnswer)
        if (err := self._err(data)):
            return {"ok": False, "error": err}
        d = data.model_dump()
        return {
            "ok": True,
            "model_answer": str(d.get("model_answer") or "").strip(),
            "covers": _str_list(d.get("covers")),
        }

    # ── 3c. improvement opportunities (candidate-facing, forward-looking) ───────
    def improvement_opportunities(self, records: list[dict], job: dict, cv_text: str,
                                  lang: str = "en", profile: dict | None = None) -> dict:
        """Candidate-facing re-read: from the CV/profile plus the answers given,
        rank the BIGGEST opportunities to improve this candidate's chances for the role.

        `records` = [{question, answer, score?, verdict?, ...}] (same shape the
        scorecard already holds). Returns {"ok", "opportunities":[{title, rationale,
        action, impact}], "summary"} — ranked, each with a concrete how-to."""
        answered = [r for r in (records or []) if (r.get("answer") or "").strip()]
        if not answered:
            return {"ok": False, "error": "no answered questions to analyze yet"}
        lang_note = ic.LANG_NOTE.get(lang, ic.LANG_NOTE["en"])
        lines = []
        for i, r in enumerate(answered, 1):
            lines.append(
                f"Q{i}: {r.get('question', '')}\n"
                f"  Answer: {(r.get('answer') or '')[:600]}"
                + (f"  (scored {r['score']})" if r.get("score") is not None else "")
            )
        instructions = ic.OPPORTUNITIES_PROMPT + lang_note
        prompt = (self._context(job, cv_text, profile)
                  + "\n\nANSWERS GIVEN SO FAR:\n" + "\n\n".join(lines))
        data = self._call_parsed(instructions, prompt, ic.OpportunityList)
        if (err := self._err(data)):
            return {"ok": False, "error": err}
        d = data.model_dump()
        return {
            "ok": True,
            "opportunities": _coerce_opportunities(d.get("opportunities")),
            "summary": str(d.get("summary") or "").strip(),
        }

    # ── 4. live candidate assessment (aspects, updated as answers come in) ──────
    def assess_candidate(self, job: dict, cv_text: str, profile: dict | None,
                         records: list[dict], lang: str = "en",
                         prior_aspects: list[dict] | None = None) -> dict:
        """The helper's own running read of the candidate across the KEY ASPECTS for
        the role. Re-scored every time a new answer is recorded, so the picture
        evolves through the interview.

        Returns {"ok", "aspects":[{aspect, score, status, note}], "summary"}.
        `prior_aspects` (the last result) is passed back so aspect NAMES stay stable
        and only their scores/notes move as evidence accrues."""
        answered = [r for r in (records or []) if (r.get("answer") or "").strip()]
        lang_note = ic.LANG_NOTE.get(lang, ic.LANG_NOTE["en"])

        if answered:
            lines = "\n".join(
                f"Q{i}: {r.get('question', '')}\n  Answer: {(r.get('answer') or '')[:600]}"
                + (f"  (scored {r['score']})" if r.get("score") is not None else "")
                for i, r in enumerate(answered, 1)
            )
            answers_block = "\n\nINTERVIEW ANSWERS SO FAR (strongest evidence):\n" + lines
        else:
            answers_block = ("\n\nNo interview answers recorded yet — base each aspect on the "
                             "CV and profile, and mark anything not yet evidenced in an "
                             "interview with status 'unknown'.")

        prior_block = ""
        if prior_aspects:
            prior_block = ("\n\nASPECTS SO FAR — keep these same aspect NAMES and only update "
                           "their score/status/note as new answers warrant:\n"
                           + json.dumps(prior_aspects, ensure_ascii=False))

        instructions = ic.ASSESS_PROMPT + lang_note
        prompt = self._context(job, cv_text, profile) + prior_block + answers_block
        data = self._call_parsed(instructions, prompt, ic.AspectAssessment)
        if (err := self._err(data)):
            return {"ok": False, "error": err}
        d = data.model_dump()
        return {
            "ok": True,
            "aspects": _coerce_aspects(d.get("aspects")),
            "summary": str(d.get("summary") or "").strip(),
        }


# ══════════════════════════════════════════════════════════════════════════════
#  Post-processing helpers — normalise the Structured-Outputs payloads
#  (clamp scores, cap list lengths, apply the `final`/exhausted business rules).
#  Structured Outputs guarantees the SHAPE; these enforce the value bounds and the
#  interview-specific defaulting the schema can't express.
# ══════════════════════════════════════════════════════════════════════════════
def _clamp_score(v) -> int | None:
    try:
        n = int(round(float(v)))
    except (TypeError, ValueError):
        return None
    return max(0, min(100, n))


def _str_list(v, limit: int = 6) -> list[str]:
    if not isinstance(v, list):
        return []
    out = [str(x).strip() for x in v if str(x).strip()]
    return out[:limit]


def _coerce_questions(raw) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out = []
    for i, q in enumerate(raw, 1):
        if isinstance(q, dict):
            text = str(q.get("question") or "").strip()
            note = str(q.get("note") or "").strip()
            qid = q.get("id")
        else:
            text, note, qid = str(q).strip(), "", i
        if not text:
            continue
        try:
            qid = int(qid)
        except (TypeError, ValueError):
            qid = i
        out.append({"id": qid, "question": text, "note": note})
    return out


def _coerce_parsed(raw) -> list[dict]:
    """Shape the model's parse output into [{id, question, answer}], dropping blanks."""
    if not isinstance(raw, list):
        return []
    out = []
    for q in raw:
        if isinstance(q, dict):
            text = str(q.get("question") or "").strip()
            ans = str(q.get("answer") or "").strip()
        else:
            text, ans = str(q).strip(), ""
        if not text:
            continue
        out.append({"id": len(out) + 1, "question": text, "answer": ans})
    return out


_ANALYSIS_STATUSES = ("answer", "clarifying", "partial")


def _coerce_analysis(data: dict, force_complete: bool = False) -> dict:
    # `complete` defaults True so legacy responses (without the field) still score.
    complete = bool(data.get("complete", True)) or force_complete
    status = str(data.get("status") or "").strip().lower()
    if status not in _ANALYSIS_STATUSES:
        status = "answer" if complete else "partial"
    return {
        "complete": complete,
        "status": status,
        "needs": str(data.get("needs") or "").strip(),
        # No committed score until the exchange is a complete answer.
        "score": _clamp_score(data.get("score")) if complete else None,
        "verdict": str(data.get("verdict") or "").strip(),
        "strengths": _str_list(data.get("strengths")),
        "concerns": _str_list(data.get("concerns")),
        "signals": _str_list(data.get("signals")),
    }


def _coerce_followup(data: dict) -> dict:
    """Shape the follow-up suggestion. Defensive: an empty question always means the
    thread is exhausted, even if the model forgot to set the flag."""
    if not isinstance(data, dict):
        return {"exhausted": True, "question": "", "note": "", "reason": ""}
    question = str(data.get("question") or "").strip()
    exhausted = bool(data.get("exhausted")) or not question
    return {
        "exhausted": exhausted,
        "question": "" if exhausted else question,
        "note": str(data.get("note") or "").strip(),
        "reason": str(data.get("reason") or "").strip(),
    }


_ASPECT_STATUSES = ("strong", "mixed", "weak", "unknown")


def _coerce_aspects(raw) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out = []
    for a in raw:
        if not isinstance(a, dict):
            continue
        name = str(a.get("aspect") or a.get("name") or "").strip()
        if not name:
            continue
        status = str(a.get("status") or "").strip().lower()
        if status not in _ASPECT_STATUSES:
            status = "unknown"
        out.append({
            "aspect": name,
            "score": _clamp_score(a.get("score")),
            "status": status,
            "note": str(a.get("note") or "").strip(),
        })
    return out[:8]


_IMPACT_LEVELS = ("high", "medium", "low")


def _coerce_opportunities(raw) -> list[dict]:
    """Shape the improvement opportunities into [{title, rationale, action, impact}],
    defaulting an unrecognised impact to 'medium' and dropping title-less entries."""
    if not isinstance(raw, list):
        return []
    out = []
    for o in raw:
        if not isinstance(o, dict):
            continue
        title = str(o.get("title") or "").strip()
        if not title:
            continue
        impact = str(o.get("impact") or "").strip().lower()
        if impact not in _IMPACT_LEVELS:
            impact = "medium"
        out.append({
            "title": title,
            "rationale": str(o.get("rationale") or "").strip(),
            "action": str(o.get("action") or "").strip(),
            "impact": impact,
        })
    return out[:6]


def _others_block(others, limit: int = 8, ans_chars: int = 400) -> str:
    """Compact 'interview so far' digest of OTHER answered questions, for cross-answer
    context (so a score / follow-up can account for what the candidate said elsewhere).
    Trimmed and capped to stay within the token budget; returns '' when empty."""
    if not isinstance(others, list):
        return ""
    lines = []
    for r in others:
        if not isinstance(r, dict):
            continue
        q = str(r.get("question") or "").strip()
        a = str(r.get("answer") or "").strip()
        if not q or not a:
            continue
        score = r.get("score")
        score_txt = f" (scored {score})" if score is not None else ""
        lines.append(f"  Q: {q}\n    A: {a[:ans_chars]}{score_txt}")
        if len(lines) >= limit:
            break
    if not lines:
        return ""
    return "\n\nINTERVIEW SO FAR (other answered questions, for context):\n" + "\n".join(lines)


def _profile_text(profile) -> str:
    """Render the recruiter's structured candidate profile + AI summary into a
    compact text block for the prompt. Tolerant of missing fields."""
    if not isinstance(profile, dict):
        return ""
    lines = []
    labels = [
        ("title", "Title"), ("seniority", "Seniority"),
        ("experience_years", "Experience"), ("years_experience", "Experience"),
        ("location", "Location"), ("languages", "Languages"),
        ("industry", "Industry"), ("role_category", "Role"),
        ("education", "Education"), ("education_level", "Education"),
        ("salary_expectation", "Salary expectation"), ("availability", "Availability"),
    ]
    seen = set()
    for key, label in labels:
        if label in seen:
            continue
        v = profile.get(key)
        if v:
            lines.append(f"{label}: {v}")
            seen.add(label)
    skills = profile.get("top_skills") or profile.get("skills")
    if isinstance(skills, list) and skills:
        lines.append("Skills: " + ", ".join(str(s) for s in skills))
    elif isinstance(skills, str) and skills.strip():
        lines.append("Skills: " + skills.strip())
    summary = profile.get("ai_summary") or profile.get("summary")
    if summary:
        lines.append("Summary: " + str(summary))
    return "\n".join(lines)
