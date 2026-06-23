"""
config.py — settings for the `interview` service (flat constants, per rework §5).

The single home for this module's knobs: the model, the shared prompt building blocks
(RUBRIC, CALIBRATION, LANG_NOTE), the per-call instruction templates, and the
Structured-Outputs Pydantic schemas each call is constrained to. The orchestrator
assembles the dynamic parts (job/CV context, the `final` gate, follow-up threads) from
these constants; the constants themselves live here so the wording is tunable in one place.

Adopted Structured Outputs in rework 2.3 #3: every interview call uses
`responses.parse(text_format=<schema below>)` → validated `output_parsed`, so the prompts
no longer beg the model for "ONLY valid JSON in this exact shape".
"""
from typing import Literal, Optional

from pydantic import BaseModel

from jobs_intelligence_ai import config

# All interview calls use the shared reasoning model.
MODEL = config.CHAT_MODEL


# ── shared prompt building blocks ──────────────────────────────────────────────
# How an answer is judged. A fixed rubric applied to every answer, independent of the
# interview question being answered. Kept here (not inline) so it reads as one list.
RUBRIC = (
    "Score the answer 0-100 on how well it resolves the concern the question "
    "probes, weighing: (1) RELEVANCE — does it actually address what was asked; "
    "(2) EVIDENCE — concrete examples, numbers, named projects, outcomes, rather "
    "than generic claims; (3) DEPTH — does it show real understanding and "
    "ownership versus surface familiarity; (4) COMMUNICATION — is it clear and "
    "structured. A vague or evasive answer scores low even if confident; a "
    "specific, quantified, first-hand answer scores high."
)

# Every judgement (questions, answer scores, running assessment) must be measured
# against the level the posting actually asks for — not an abstract ideal. Shared by
# all prompts so calibration is consistent.
CALIBRATION = (
    " Calibrate all expectations to the SENIORITY and EXPERIENCE the posting asks "
    "for. Read the job title and description for level cues — e.g. 'junior', "
    "'graduate', 'working student', 'medior', 'senior', 'lead', 'head of', or a "
    "stated bar like '2+ years' or '5+ years' — and judge against THAT level: do "
    "not penalise a junior/entry role for lacking senior-level depth, and do "
    "demand more from a senior/lead role. Also weigh how each requirement is "
    "PHRASED: treat hard 'must-have' / 'required' items as more decisive than "
    "'nice to have' / 'a plus' / 'desirable' ones."
)

LANG_NOTE = {
    "en": " Write all text fields in English.",
    "de": " Write all text fields in German.",
    "sk": " Write all text fields in Slovak.",
    "auto": " Write all text fields in the same language as the job description.",
}


# ── 1. generate_questions ──────────────────────────────────────────────────────
QUESTIONS_PROMPT = (
    "You are a recruitment assistant preparing an interviewer. Compare the "
    "job and the candidate CV, find the gaps or unproven areas, and write "
    "{n} targeted interview questions that probe them. For each, add a short "
    "note naming the gap it addresses." + CALIBRATION + " Number ids from 1."
)


class _Question(BaseModel):
    id: int
    question: str
    note: str


class QuestionList(BaseModel):
    """gap-based interview questions, each carrying the gap it probes."""
    questions: list[_Question]


# ── 1b. parse_questions (import a prepared document) ────────────────────────────
PARSE_PROMPT = (
    "You are given a prepared interview document as free-form text. It contains "
    "interview QUESTIONS and, after some of them, the candidate's ANSWER. There "
    "are no explicit labels: questions and answers simply alternate, and NOT "
    "every question has an answer. A question is what the interviewer asks (it "
    "need not end in '?'); an answer is the candidate's reply, usually "
    "first-person. Extract them IN ORDER. For each question give its text and "
    "the answer that immediately follows it — use an empty string when the next "
    "item is another question or the document ends. Preserve the original "
    "wording and language EXACTLY: do not translate, summarise, merge, or "
    "invent. Number ids from 1."
)


class _ParsedQA(BaseModel):
    id: int
    question: str
    answer: str


class ParsedQAList(BaseModel):
    """ordered Q/A pairs extracted from a prepared document; answer is "" when absent."""
    questions: list[_ParsedQA]


# ── 2. analyze_answer ──────────────────────────────────────────────────────────
# The gate + scoring instructions are assembled by the orchestrator (the `final`
# override changes the middle), so they live as separate pieces here.
ANALYZE_GATE = (
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
ANALYZE_FINAL_NOTE = (
    "The interviewer has marked this answer FINAL: treat it as complete "
    "and score it as it stands, even if brief or partial. "
)
ANALYZE_OPEN_NOTE = (
    "If the exchange is NOT yet a complete answer, set \"complete\" false, "
    "set \"score\" null, and in \"needs\" briefly state what the candidate "
    "asked for or what is still missing and what the interviewer should do "
    "next. Only when it is a complete answer set \"complete\" true and "
    "score it. "
)
ANALYZE_SCORING = (
    "When scoring a complete answer: " + RUBRIC + CALIBRATION +
    " Also surface SIGNALS — qualities the answer reveals that aren't explicitly "
    "asked for (e.g. strategic thinking, ownership, commercial awareness, "
    "quantitative rigour, or asking sharp clarifying questions) — as short tags. "
    "Judge the WHOLE exchange, not just the first turn. Use status "
    "'answer' | 'clarifying' | 'partial' for the latest turn, and leave score null "
    "unless the exchange is a complete answer."
)


class AnswerAnalysis(BaseModel):
    """one turn of a live interview: whether it's complete, and (when complete) its score."""
    complete: bool
    status: Literal["answer", "clarifying", "partial"]
    needs: str
    score: Optional[int]
    verdict: str
    strengths: list[str]
    concerns: list[str]
    signals: list[str]


# ── 2b. suggest_followup ───────────────────────────────────────────────────────
FOLLOWUP_PROMPT = (
    "You are conducting a live interview. Below is ONE line of questioning: the "
    "original question, the candidate's answer, and any follow-ups already asked "
    "with their answers. Decide whether ONE more follow-up would meaningfully "
    "improve your read of the candidate ON THIS TOPIC. Propose a follow-up ONLY "
    "when the latest answer leaves a genuine unresolved gap, an unverified or "
    "vague claim, or a promising thread worth exactly one more probe. If the topic "
    "is already well covered, the answer is specific and complete, or further "
    "probing would be redundant, STOP: set \"exhausted\" to true and leave "
    "\"question\" empty. Ask at most one question at a time." + CALIBRATION
)


class Followup(BaseModel):
    """ONE proposed follow-up for a line of questioning, or exhausted=true to stop."""
    exhausted: bool
    question: str
    note: str
    reason: str


# ── 3. summarize ───────────────────────────────────────────────────────────────
SUMMARIZE_PROMPT = (
    "You are a hiring manager writing the wrap-up of an interview from the "
    "scored answers below. Give an overall fit score 0-100 (consider both "
    "the individual scores and how the answers hang together), a one-word/"
    "short recommendation (e.g. 'Advance', 'Hold', 'Pass'), and a 2-3 "
    "sentence summary covering the strongest evidence and the biggest "
    "remaining risk." + CALIBRATION
)


class InterviewSummary(BaseModel):
    """overall read across the answered questions."""
    score: int
    recommendation: str
    summary: str


# ── 3b. model_answer (candidate coaching) ──────────────────────────────────────
MODEL_ANSWER_PROMPT = (
    "You are an interview coach helping a CANDIDATE. Given the role and the "
    "candidate's background, explain what a STRONG answer to this interview "
    "question would cover — the substance, concrete evidence and framing the "
    "company is really looking for. Tailor it to THIS role; where the "
    "candidate's CV gives them something real to draw on, point that out. "
    "Coach the candidate on what to convey — do NOT write a word-for-word "
    "script for them to recite. Give 2-4 sentences of guidance and the key "
    "points a strong answer hits." + CALIBRATION
)


class ModelAnswer(BaseModel):
    """coaching for the candidate: what a strong answer to this question covers."""
    model_answer: str
    covers: list[str]


# ── 3c. improvement_opportunities ──────────────────────────────────────────────
OPPORTUNITIES_PROMPT = (
    "You are a candidate's interview coach. From the role, the candidate's "
    "CV/profile, and the answers they have given, identify the BIGGEST "
    "opportunities for this candidate to improve their chances for THIS role. "
    "Rank 3-5 of them by how much each would move the company's decision. For "
    "each give: a short title (the opportunity), a one-line rationale (why it "
    "matters for this role), a concrete ACTION the candidate can take (a "
    "strength to surface, evidence to add, an answer to sharpen, a gap to "
    "close), and an impact tag 'high' | 'medium' | 'low'. Be specific and "
    "constructive — never generic filler. Close with a 2-3 sentence "
    "encouraging overview." + CALIBRATION
)


class _Opportunity(BaseModel):
    title: str
    rationale: str
    action: str
    impact: Literal["high", "medium", "low"]


class OpportunityList(BaseModel):
    """ranked ways the candidate can improve their chances, each with a how-to."""
    opportunities: list[_Opportunity]
    summary: str


# ── 4. assess_candidate ────────────────────────────────────────────────────────
ASSESS_PROMPT = (
    "You are continuously assessing a candidate for a specific role across the "
    "KEY ASPECTS that matter for it. Pick 4-6 aspects inferred from the job and "
    "candidate (e.g. core technical skills, domain/industry experience, relevant "
    "seniority, communication, and any role-specific competencies). For EACH "
    "aspect give: a score 0-100, a status of 'strong' | 'mixed' | 'weak' | "
    "'unknown', and a one-line note citing the evidence. Interview answers are the "
    "strongest evidence as they accumulate; the CV and profile are the baseline. "
    "If an aspect has no evidence yet, use status 'unknown'." + CALIBRATION +
    " Also give a 2-3 sentence overall summary."
)


class _Aspect(BaseModel):
    aspect: str
    score: int
    status: Literal["strong", "mixed", "weak", "unknown"]
    note: str


class AspectAssessment(BaseModel):
    """the helper's running read of the candidate across the key aspects for the role."""
    aspects: list[_Aspect]
    summary: str
