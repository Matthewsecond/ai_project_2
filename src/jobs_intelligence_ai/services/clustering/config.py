"""
config.py — settings for the `clustering` service (flat constants, per rework §5).

The single home for this module's knobs: the embedding model + clustering granularity, the
persona-synthesis prompt + its Structured-Outputs schema, and the segment-chat system prompt
+ language map. The persona call was converted to Structured Outputs in rework 2.3 #6
(`responses.parse(text_format=PersonaResult)` → validated `output_parsed`, no "ONLY JSON"
boilerplate); segment chat is text-only.
"""
from pydantic import BaseModel

from jobs_intelligence_ai import config

# Models (sourced from global).
EMBEDDING_MODEL = config.EMBEDDING_MODEL   # batched candidate-profile embeddings
CHAT_MODEL      = config.CHAT_MODEL         # persona synthesis + segment chat

# Default dendrogram-cut granularity (0 coarse → 1 fine) for cluster_labels().
DEFAULT_GRANULARITY = 0.5


# ── persona.synthesize_persona ─────────────────────────────────────────────────
PERSONA_PROMPT = (
    "You are a recruitment analyst. You are given several candidate profiles that were "
    "grouped into ONE talent segment. Describe the SEGMENT as a whole, not each person.\n"
    '  "title": a 3-5 word label for the segment (e.g. "Senior B2B SaaS sellers")\n'
    '  "summary": one sentence describing the shared role focus and seniority\n'
    '  "persona_text": a synthetic candidate profile of 5-8 lines capturing the segment\'s '
    "common role focus, seniority, core skills, tools, and languages — written like a concise "
    "CV summary so it can be matched against job postings.\n"
    "Respond in English."
)


class PersonaResult(BaseModel):
    """synthetic candidate representing one talent segment."""
    title: str
    summary: str
    persona_text: str


# ── segment_chat.send_segment_message ──────────────────────────────────────────
SEGMENT_SYSTEM = """You are an assistant explaining a TALENT SEGMENT that was produced by clustering candidate CVs by similarity (embeddings). Answer the recruiter's questions about this segment — why these candidates were grouped together, their shared profile, how individuals differ, and how they fit the matched roles. Refer to candidates by name.

SEGMENT: {title}
SUMMARY: {summary}
PERSONA (synthetic profile representing the segment):
{persona}

CANDIDATES IN THIS SEGMENT:
{members}

MATCHED ROLES (the A/B grade reflects the segment's fit):
{jobs}

Rules:
1. Stay focused on THIS segment, its candidates, and its roles.
2. Be concise — 2–4 sentences unless asked for more detail.
3. {{LANG_INSTRUCTION}}
4. The grouping is by overall CV similarity; if asked why someone is included, explain via their shared skills/role/seniority, and note honestly if they look like a weaker fit for the cluster.
"""

LANG_INSTRUCTIONS = {
    "en":   "Always respond in English, regardless of the job description language or what language the user writes in.",
    "de":   "Antworte immer auf Deutsch, unabhängig von der Sprache der Stellenbeschreibung oder der Nutzernachricht.",
    "sk":   "Vždy odpovedaj po slovensky, bez ohľadu na jazyk inzerátu alebo správy používateľa.",
    "auto": "Respond in the same language the user writes in.",
}


# ── segment_analysis.segment_overview ───────────────────────────────────────────
# Cross-segment opportunity overview. Converted to Structured Outputs in rework 2.4 — prose
# output, so SegmentOverview is a single `text` field (was a bare responses.create in the bp).
OVERVIEW_MODEL = config.CHAT_MODEL

OVERVIEW_PROMPT = (
    "You are a recruitment strategy analyst writing for an HR / recruitment lead. "
    "Each segment is a cluster of similar candidates, with how many candidates we have "
    "and how many strong (A/B grade) job openings matched that profile. Write a concise "
    "OPPORTUNITY OVERVIEW (~150–220 words) that: (1) ranks where the biggest opportunity "
    "is — segments with many strong open roles relative to the number of candidates "
    "(high demand, easy to place / worth sourcing more), (2) flags oversupplied segments "
    "(many candidates but few matching roles → competition / harder to place), and "
    "(3) gives 2–4 concrete recommendations on where to focus. Refer to segments by name "
    "and cite the role/candidate counts. Use short paragraphs or bullets. Respond in English."
)


class SegmentOverview(BaseModel):
    """cross-segment opportunity overview (prose)."""
    text: str


# ── segment_analysis.grade_candidates_for_job ───────────────────────────────────
# Opt-in precise grading: score each candidate against ONE job. Converted to Structured
# Outputs in rework 2.4 — replaces the "ONLY a JSON array" prompt + search_utils.parse_json.
GRADE_MODEL = config.CHAT_MODEL

GRADE_PROMPT = (
    "Score how well EACH candidate fits THIS job. For every candidate, IN THE SAME ORDER as "
    "given, return a score from 0.0 to 1.0 and one short sentence reason. Use the full range; "
    "judge genuine fit, not keyword overlap."
)


class _CandidateGrade(BaseModel):
    score: float
    reason: str


class CandidateGrades(BaseModel):
    """per-candidate fit scores for one job, in the same order as the input candidates."""
    candidates: list[_CandidateGrade]
