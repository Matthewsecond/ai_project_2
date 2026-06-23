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
