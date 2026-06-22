"""
services/interview_helper.py — Live interview scoring for the job-detail modal.

`InterviewHelper` owns the whole interview loop for one (candidate, job) pair:

    generate_questions(job, cv_text)  → gap-based questions to ask
    analyze_answer(question, answer)  → score + qualitative read of one answer
    summarize(records)                → overall recommendation across answers

It is deliberately a small class rather than a few inline endpoint functions so
the evaluation RUBRIC (how an answer is judged) lives in one place, separate from
the interview questions themselves. The recruiter records what the candidate said
against each question; each answer is scored 0–100 and tagged with strengths,
concerns, and soft signals (e.g. "strategic thinking") that aren't on the nose.

All AI calls go through the shared OpenAI client (`core.get_client`) and use
`config.CHAT_MODEL`, matching the other AI features. Every method degrades to a
structured error dict instead of raising, so a flaky model call never 500s the
interview UI.
"""
import json
import logging
import re

from jobs_intelligence_ai import config

logger = logging.getLogger(__name__)

# How an answer is judged. This is the "analysis questions" the recruiter asked
# for — a fixed rubric applied to every answer, independent of the interview
# question being answered. Kept here (not in the prompt strings) so it reads as
# one list and is easy to tune.
_RUBRIC = (
    "Score the answer 0-100 on how well it resolves the concern the question "
    "probes, weighing: (1) RELEVANCE — does it actually address what was asked; "
    "(2) EVIDENCE — concrete examples, numbers, named projects, outcomes, rather "
    "than generic claims; (3) DEPTH — does it show real understanding and "
    "ownership versus surface familiarity; (4) COMMUNICATION — is it clear and "
    "structured. A vague or evasive answer scores low even if confident; a "
    "specific, quantified, first-hand answer scores high."
)

# Every judgement (questions, answer scores, running assessment) must be measured
# against the level the posting actually asks for — not an abstract ideal. Shared
# by all three prompts so calibration is consistent.
_CALIBRATION = (
    " Calibrate all expectations to the SENIORITY and EXPERIENCE the posting asks "
    "for. Read the job title and description for level cues — e.g. 'junior', "
    "'graduate', 'working student', 'medior', 'senior', 'lead', 'head of', or a "
    "stated bar like '2+ years' or '5+ years' — and judge against THAT level: do "
    "not penalise a junior/entry role for lacking senior-level depth, and do "
    "demand more from a senior/lead role. Also weigh how each requirement is "
    "PHRASED: treat hard 'must-have' / 'required' items as more decisive than "
    "'nice to have' / 'a plus' / 'desirable' ones."
)

_LANG_NOTE = {
    "en": " Write all text fields in English.",
    "de": " Write all text fields in German.",
    "sk": " Write all text fields in Slovak.",
    "auto": " Write all text fields in the same language as the job description.",
}


class InterviewHelper:
    """Stateless helper — one instance is reused across requests; the interview
    record itself is held by the caller (front-end / saved-job extras)."""

    def __init__(self, client=None, model: str | None = None):
        self._client = client
        self._model = model or config.CHAT_MODEL

    # ── client / low-level call ────────────────────────────────────────────────
    @property
    def client(self):
        if self._client is None:
            from jobs_intelligence_ai.core import get_client
            self._client = get_client()
        return self._client

    def _call_json(self, instructions: str, prompt: str):
        """One model call expected to return JSON. Returns the parsed object, or
        a {"_error": ...} dict so callers can surface failure without raising."""
        if not config.OPENAI_API_KEY:
            return {"_error": "Interview features require an OpenAI API key — add OPENAI_API_KEY to your .env file."}
        try:
            resp = self.client.responses.create(
                model=self._model, instructions=instructions, input=prompt)
            return _parse_json(resp.output_text or "")
        except Exception as e:
            logger.error("InterviewHelper call failed: %s", e)
            return {"_error": str(e)}

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
        lang_note = _LANG_NOTE.get(lang, _LANG_NOTE["en"])
        instructions = (
            "You are a recruitment assistant preparing an interviewer. Compare the "
            "job and the candidate CV, find the gaps or unproven areas, and write "
            f"{n} targeted interview questions that probe them. For each, add a short "
            "note naming the gap it addresses." + _CALIBRATION +
            " Return ONLY valid JSON in this exact "
            'shape: {"questions":[{"id":1,"question":"<text>","note":"<gap it '
            'addresses>"}]}. Number ids from 1.' + lang_note
        )
        data = self._call_json(instructions, self._context(job, cv_text, profile))
        if "_error" in data:
            return {"ok": False, "error": data["_error"]}
        questions = _coerce_questions(data.get("questions"))
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
        instructions = (
            "You are given a prepared interview document as free-form text. It contains "
            "interview QUESTIONS and, after some of them, the candidate's ANSWER. There "
            "are no explicit labels: questions and answers simply alternate, and NOT "
            "every question has an answer. A question is what the interviewer asks (it "
            "need not end in '?'); an answer is the candidate's reply, usually "
            "first-person. Extract them IN ORDER. For each question give its text and "
            "the answer that immediately follows it — use an empty string when the next "
            "item is another question or the document ends. Preserve the original "
            "wording and language EXACTLY: do not translate, summarise, merge, or "
            'invent. Return ONLY valid JSON: {"questions":[{"id":1,"question":"<text>",'
            '"answer":"<text or empty>"}]}. Number ids from 1.'
        )
        data = self._call_json(instructions, text[:12000])
        if "_error" in data:
            return {"ok": False, "error": data["_error"]}
        questions = _coerce_parsed(data.get("questions"))
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
        lang_note = _LANG_NOTE.get(lang, _LANG_NOTE["en"])
        gate = (
            "You are an expert interviewer assessing a candidate during a LIVE, ongoing "
            "interview. You are shown one interview question and the exchange so far — "
            "the candidate's reply, plus any interviewer clarifications and further "
            "replies. FIRST decide whether the exchange is already a COMPLETE answer or "
            "still IN PROGRESS. The candidate's latest turn may be: a clarifying or "
            "scoping question back to the interviewer (e.g. asking what data, format, "
            "tools or constraints apply); a partial answer that clearly needs more; or a "
            "complete answer. A clarifying or scoping question is a normal and often "
            "POSITIVE move (it can show curiosity, rigour or real-world experience) — "
            "never treat it as a failed or weak answer. "
        )
        if final:
            gate += ("The interviewer has marked this answer FINAL: treat it as complete "
                     "and score it as it stands, even if brief or partial. ")
        else:
            gate += ("If the exchange is NOT yet a complete answer, set \"complete\" false, "
                     "set \"score\" null, and in \"needs\" briefly state what the candidate "
                     "asked for or what is still missing and what the interviewer should do "
                     "next. Only when it is a complete answer set \"complete\" true and "
                     "score it. ")
        instructions = (
            gate + "When scoring a complete answer: " + _RUBRIC + _CALIBRATION +
            " Also surface SIGNALS — qualities the answer reveals that aren't explicitly "
            "asked for (e.g. strategic thinking, ownership, commercial awareness, "
            "quantitative rigour, or asking sharp clarifying questions) — as short tags. "
            "Judge the WHOLE exchange, not just the first turn. Return ONLY valid JSON: "
            '{"complete":<true|false>,"status":"answer|clarifying|partial","needs":'
            '"<text or empty>","score":<int 0-100 or null>,"verdict":"<one sentence>",'
            '"strengths":["<short point>"],"concerns":["<short point>"],'
            '"signals":["<short tag>"]}.' + lang_note
        )
        gap = f"\nGAP THIS QUESTION PROBES: {note}" if note else ""
        prompt = (
            f"{self._context(job, cv_text, profile)}{_others_block(others)}\n\n"
            f"INTERVIEW QUESTION: {question}{gap}\n\n"
            f"THE EXCHANGE SO FAR (interviewer's notes — may be multiple turns):\n{answer[:2000]}"
        )
        data = self._call_json(instructions, prompt)
        if "_error" in data:
            return {"ok": False, "error": data["_error"]}
        return {"ok": True, **_coerce_analysis(data, force_complete=final)}

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
        lang_note = _LANG_NOTE.get(lang, _LANG_NOTE["en"])
        instructions = (
            "You are conducting a live interview. Below is ONE line of questioning: the "
            "original question, the candidate's answer, and any follow-ups already asked "
            "with their answers. Decide whether ONE more follow-up would meaningfully "
            "improve your read of the candidate ON THIS TOPIC. Propose a follow-up ONLY "
            "when the latest answer leaves a genuine unresolved gap, an unverified or "
            "vague claim, or a promising thread worth exactly one more probe. If the topic "
            "is already well covered, the answer is specific and complete, or further "
            "probing would be redundant, STOP: set \"exhausted\" to true and do NOT invent "
            "a question. Ask at most one question at a time." + _CALIBRATION +
            ' Return ONLY valid JSON: {"exhausted":<true|false>,"question":"<the follow-up, '
            'or empty if exhausted>","note":"<the gap this follow-up probes>","reason":"<if '
            'exhausted, why this thread is done>"}.' + lang_note
        )
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
        data = self._call_json(instructions, prompt)
        if "_error" in data:
            return {"ok": False, "error": data["_error"]}
        return {"ok": True, **_coerce_followup(data)}

    # ── 3. summarize the interview ─────────────────────────────────────────────
    def summarize(self, records: list[dict], job: dict, cv_text: str,
                  lang: str = "en", profile: dict | None = None) -> dict:
        """Aggregate answered questions into an overall read.

        `records` = [{question, answer, score, verdict, strengths, concerns,
        signals}]. Returns {"ok", "score", "recommendation", "summary"}."""
        answered = [r for r in (records or []) if (r.get("answer") or "").strip()]
        if not answered:
            return {"ok": False, "error": "no answered questions to summarize"}
        lang_note = _LANG_NOTE.get(lang, _LANG_NOTE["en"])
        lines = []
        for i, r in enumerate(answered, 1):
            lines.append(
                f"Q{i}: {r.get('question', '')}\n"
                f"  Answer: {(r.get('answer') or '')[:600]}\n"
                f"  Score: {r.get('score', '—')}  Verdict: {r.get('verdict', '')}"
            )
        instructions = (
            "You are a hiring manager writing the wrap-up of an interview from the "
            "scored answers below. Give an overall fit score 0-100 (consider both "
            "the individual scores and how the answers hang together), a one-word/"
            "short recommendation (e.g. 'Advance', 'Hold', 'Pass'), and a 2-3 "
            "sentence summary covering the strongest evidence and the biggest "
            "remaining risk." + _CALIBRATION + " Return ONLY valid JSON: "
            '{"score":<int 0-100>,"recommendation":"<short>","summary":"<text>"}.'
            + lang_note
        )
        prompt = self._context(job, cv_text, profile) + "\n\nSCORED ANSWERS:\n" + "\n\n".join(lines)
        data = self._call_json(instructions, prompt)
        if "_error" in data:
            return {"ok": False, "error": data["_error"]}
        return {
            "ok": True,
            "score": _clamp_score(data.get("score")),
            "recommendation": str(data.get("recommendation") or "").strip(),
            "summary": str(data.get("summary") or "").strip(),
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
        lang_note = _LANG_NOTE.get(lang, _LANG_NOTE["en"])
        instructions = (
            "You are an interview coach helping a CANDIDATE. Given the role and the "
            "candidate's background, explain what a STRONG answer to this interview "
            "question would cover — the substance, concrete evidence and framing the "
            "company is really looking for. Tailor it to THIS role; where the "
            "candidate's CV gives them something real to draw on, point that out. "
            "Coach the candidate on what to convey — do NOT write a word-for-word "
            "script for them to recite." + _CALIBRATION +
            ' Return ONLY valid JSON: {"model_answer":"<2-4 sentence guidance>",'
            '"covers":["<a key point a strong answer hits>"]}.' + lang_note
        )
        gap = f"\nGAP THIS QUESTION PROBES: {note}" if note else ""
        prompt = (self._context(job, cv_text, profile)
                  + f"\n\nINTERVIEW QUESTION: {question}{gap}")
        data = self._call_json(instructions, prompt)
        if "_error" in data:
            return {"ok": False, "error": data["_error"]}
        return {
            "ok": True,
            "model_answer": str(data.get("model_answer") or "").strip(),
            "covers": _str_list(data.get("covers")),
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
        lang_note = _LANG_NOTE.get(lang, _LANG_NOTE["en"])
        lines = []
        for i, r in enumerate(answered, 1):
            lines.append(
                f"Q{i}: {r.get('question', '')}\n"
                f"  Answer: {(r.get('answer') or '')[:600]}"
                + (f"  (scored {r['score']})" if r.get("score") is not None else "")
            )
        instructions = (
            "You are a candidate's interview coach. From the role, the candidate's "
            "CV/profile, and the answers they have given, identify the BIGGEST "
            "opportunities for this candidate to improve their chances for THIS role. "
            "Rank 3-5 of them by how much each would move the company's decision. For "
            "each give: a short title (the opportunity), a one-line rationale (why it "
            "matters for this role), a concrete ACTION the candidate can take (a "
            "strength to surface, evidence to add, an answer to sharpen, a gap to "
            "close), and an impact tag 'high' | 'medium' | 'low'. Be specific and "
            "constructive — never generic filler." + _CALIBRATION +
            ' Return ONLY valid JSON: {"opportunities":[{"title":"<text>","rationale":'
            '"<text>","action":"<text>","impact":"high|medium|low"}],"summary":'
            '"<2-3 sentence encouraging overview>"}.' + lang_note
        )
        prompt = (self._context(job, cv_text, profile)
                  + "\n\nANSWERS GIVEN SO FAR:\n" + "\n\n".join(lines))
        data = self._call_json(instructions, prompt)
        if "_error" in data:
            return {"ok": False, "error": data["_error"]}
        return {
            "ok": True,
            "opportunities": _coerce_opportunities(data.get("opportunities")),
            "summary": str(data.get("summary") or "").strip(),
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
        lang_note = _LANG_NOTE.get(lang, _LANG_NOTE["en"])

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

        instructions = (
            "You are continuously assessing a candidate for a specific role across the "
            "KEY ASPECTS that matter for it. Pick 4-6 aspects inferred from the job and "
            "candidate (e.g. core technical skills, domain/industry experience, relevant "
            "seniority, communication, and any role-specific competencies). For EACH "
            "aspect give: a score 0-100, a status of 'strong' | 'mixed' | 'weak' | "
            "'unknown', and a one-line note citing the evidence. Interview answers are the "
            "strongest evidence as they accumulate; the CV and profile are the baseline. "
            "If an aspect has no evidence yet, use status 'unknown'." + _CALIBRATION +
            " Also give a 2-3 "
            "sentence overall summary. Return ONLY valid JSON: "
            '{"aspects":[{"aspect":"<name>","score":<int 0-100>,'
            '"status":"<strong|mixed|weak|unknown>","note":"<evidence>"}],"summary":"<text>"}.'
            + lang_note
        )
        prompt = self._context(job, cv_text, profile) + prior_block + answers_block
        data = self._call_json(instructions, prompt)
        if "_error" in data:
            return {"ok": False, "error": data["_error"]}
        return {
            "ok": True,
            "aspects": _coerce_aspects(data.get("aspects")),
            "summary": str(data.get("summary") or "").strip(),
        }


# ══════════════════════════════════════════════════════════════════════════════
#  Parsing / coercion helpers — keep the model's output well-shaped
# ══════════════════════════════════════════════════════════════════════════════
def _parse_json(raw: str):
    """Parse a model response that should be a JSON object, tolerating ```json
    fences and leading/trailing prose."""
    s = (raw or "").strip()
    if s.startswith("```"):
        s = s.split("```")[1]
        if s.startswith("json"):
            s = s[4:]
        s = s.strip()
    try:
        return json.loads(s)
    except (ValueError, TypeError):
        m = re.search(r"\{.*\}", s, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except (ValueError, TypeError):
                pass
    return {"_error": "could not parse model response"}


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
