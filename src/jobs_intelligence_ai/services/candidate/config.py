"""
config.py — settings for the `candidate` service (flat constants, per rework §5).

Home for this module's LLM call prompts + Structured-Outputs schemas: the LinkedIn profile
enricher, the CV text parser, and the guided target-candidate builder chat. The DB store and
the example-CV PDF builders have no model call, so nothing about them lives here.
"""
from typing import Literal, Optional

from pydantic import BaseModel

from jobs_intelligence_ai import config

CHAT_MODEL = config.CHAT_MODEL
CLASSIFIER_MODEL = config.CLASSIFIER_MODEL


# ── Demo reset ─────────────────────────────────────────────────────────────────
# The bundled example candidates shipped for the demo (mirror of the name set in
# frontend/static/js/candidate-examples.js). On app startup these are wiped from the
# DB so each demo run starts clean — see store.reset_demo_candidates(), called from
# frontend/app.py::create_app(). Keep in sync with the JS example list.
DEMO_CANDIDATE_NAMES = {
    "at": ["Roman Labuš", "Max Weber", "Julia Reiter", "Sophie Wagner", "Nina Fuchs",
           "Felix Kraus", "Stefan Hofer", "Thomas Gruber", "Anna Bauer"],
    "sk": ["Roman Labuš", "Marek Novák", "Lucia Horváthová", "Tomáš Kováč",
           "Zuzana Krajčíová", "Martin Šimko", "Peter Varga", "Eva Tóthová", "Jana Kováčová"],
}


# ── profile_parser.parse_candidate_profile ─────────────────────────────────────
# Extract a structured profile from a raw CV / pasted text (the "Paste CV" path on the
# search tab). Converted to Structured Outputs in rework 2.4; the model fills CandidateProfile.
PROFILE_PARSE_PROMPT = """You are a CV parser. Extract structured information from the candidate text.
- skills: up to 8 key skills.
- experience_years: a phrase like "8 years".
- seniority: infer ONE of exactly: Junior, Mid, Senior, Lead, Executive (from titles, years and scope of work).
- languages: a phrase like "German (native), English B2".
- salary_expectation: a phrase like "€2,800–3,400/month".
- availability: a phrase like "Immediately".
- summary: one concise sentence describing this candidate's profile.
For any field you cannot determine use null (and an empty list for skills)."""


class CandidateProfile(BaseModel):
    """Structured profile extracted from a candidate's raw CV text."""
    name: Optional[str]
    title: Optional[str]
    seniority: Optional[str]
    experience_years: Optional[str]
    skills: list[str]
    location: Optional[str]
    languages: Optional[str]
    salary_expectation: Optional[str]
    availability: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    linkedin: Optional[str]
    summary: Optional[str]


# ── profile_enricher.enrich_linkedin_profile ───────────────────────────────────
ENRICH_PROMPT = """You are a senior recruiter analyzing a candidate's LinkedIn profile for the Austrian job market.
Read the raw profile JSON and produce a normalized, recruiter-ready structured record.
INFER where reasonable (seniority, total years of experience, industry, salary) from the
work history, titles, skills and dates — do not merely copy fields. Be conservative: never
invent specific employers, credentials or facts not supported by the data.

Salaries in this market are AUSTRIAN MONTHLY GROSS in euros (~14 salaries/year). Estimate a
realistic monthly-gross range for this candidate's role, seniority and location. This is an
ESTIMATE derived from the role — LinkedIn does not provide it.

For fields you genuinely cannot determine, use null (or an empty list). For seniority pick
exactly one of: Junior, Mid, Senior, Lead, Executive. years_experience and the salary
estimates are integers (monthly gross EUR for salary)."""

# AI-inferred keys merged over the mechanical base, in order.
AI_KEYS = (
    "name", "title", "current_company", "headline", "seniority", "years_experience",
    "industry", "role_category", "education_level", "management_experience",
    "top_skills", "specializations", "languages", "location", "ai_summary",
    "strengths", "estimated_salary_min", "estimated_salary_max",
)


class LinkedInProfile(BaseModel):
    """Normalized recruiter-ready profile inferred from a raw LinkedIn scrape."""
    name: str
    title: str
    current_company: Optional[str]
    headline: str
    seniority: Literal["Junior", "Mid", "Senior", "Lead", "Executive"]
    years_experience: Optional[int]
    industry: str
    role_category: str
    education_level: Optional[str]
    management_experience: str
    top_skills: list[str]
    specializations: list[str]
    languages: str
    location: str
    ai_summary: str
    strengths: list[str]
    estimated_salary_min: Optional[int]
    estimated_salary_max: Optional[int]


# ── guided_builder (2.4) ─────────────────────────────────────────────────────────
# The guided "target candidate" builder chat on the Guided tab: a two-pass turn that
# (1) extracts the spec field updates the HR manager's message implies, then (2) phrases a
# data-grounded reply + the single next narrowing question and its quick-pick chips. Both
# converted to Structured Outputs in rework 2.4, replacing the two responses.create + json.loads
# calls (and the two "Return ONLY valid JSON" prompts) that used the shared `_gpt_json` helper.
# The blueprint owns all the grounding (live DB faceting, the taxonomy catalog, salary
# benchmarks) and passes it in pre-rendered; these prompts only describe the model's job.
GUIDED_MODEL = config.CHAT_MODEL

GUIDED_EXTRACT_PROMPT = """You help an HR manager build a "target candidate" spec by extracting structured fields from what they say.
Current draft so far: {draft}
The HR manager already set these fields by hand — do NOT change them unless this message explicitly does: {locked}
{offer}
{salary}

Most fields are FREE-TEXT. Capture the user's own wording — do NOT invent specifics they didn't give. Broad answers are fine for free-text fields; record them as stated.
For states, prefer the official Austrian region name when the user clearly means one (e.g. "Vienna" → "Wien", "Lower Austria" → "Niederösterreich"), but keep anything else verbatim.

ANSWER CONTEXT — your previous question asked the user to provide: {last_field}. If this message reads as a direct answer to THAT question, file it under that exact field and nowhere else. In particular, when the field is "skills", "certs" or "languages", do NOT reclassify the answer as a "sector" just because it mentions a technology (e.g. asked for skills, user says "SAP ERP" → add "SAP ERP" to skills, do NOT touch sector). Only deviate if the user clearly changed the subject.

SECTOR CLASSIFICATION — the one fixed field. Classify the target into one or more SECTORS from this catalog, and output their IDS in "sector":
{catalog}
Rules: set "sector" ONLY when this message actually indicates the field/industry (e.g. "IT", "a nurse", "warehouse staff", "SAP consultant" → ["it"]). A specific role implies its sector (e.g. "electrician" → ["construction"], "chef" → ["hospitality"]). Use MULTIPLE ids only if the target genuinely spans sectors. If the message gives no usable sector signal, leave "sector" empty (do not guess). Output the short ids exactly as in the catalog, never the labels.

Provide ONLY the field updates this message gives information for:
  roles      — target roles / job titles to ADD — the specific role(s), only NEW ones
  skills     — skills to ADD
  levels     — seniority, e.g. Senior or Mid
  states     — regions / locations
  sector     — sector IDS from the catalog above (never the labels)
  languages  — languages with level, e.g. German C1
  certs      — certifications / licenses
  salary     — salary band string, e.g. >4000 or 4500-5500 — replaces the prior value
  availability — e.g. immediate or 2026-09 — replaces the prior value
  name       — short label for this target candidate, e.g. 'Senior SAP Logistics — Wien'
List fields are items to ADD. Leave a field empty (empty list, or null for the scalars) when the message says nothing about it."""


class GuidedFieldUpdates(BaseModel):
    """The target-spec fields a guided message implies — lists are items to ADD, scalars replace.
    Only the fields the message actually mentions are non-empty; the rest stay null/empty."""
    roles: Optional[list[str]] = None
    skills: Optional[list[str]] = None
    levels: Optional[list[str]] = None
    states: Optional[list[str]] = None
    sector: Optional[list[str]] = None
    languages: Optional[list[str]] = None
    certs: Optional[list[str]] = None
    salary: Optional[str] = None
    availability: Optional[str] = None
    name: Optional[str] = None


GUIDED_REPLY_PROMPT = """You are a proactive recruitment assistant guiding an HR manager through building a target-candidate spec. Your job is to NARROW the target step by step using REAL data.
The HR manager said: "{message}"
Your previous question to them was: "{last_question}"
You applied these field updates: {field_updates}
The HR manager also manually changed these fields since your last reply: {user_edits}
The full draft now is: {draft}

Live data from the job database for the target so far:
{facets}

Salary reference (real market data; use ONLY when salary is the topic): {salary_hint}

Write your reply and question in {lang}. The live data uses the German AMS taxonomy, so occupational groups and regions appear as German terms — when you mention them, render them naturally in {lang} (translate the term, e.g. "SoftwareentwicklerIn" → "Software Developer", "NetzwerkadministratorIn" → "Network Administrator", "Wien" → "Vienna"). Do NOT show the raw German term when writing in English. When you are writing in German, the taxonomy terms are already German — use them exactly as they appear in the data, do not anglicize them.

Style rules — this is the part that matters most:
- Sound like a sharp human recruiter, not a form. Keep "reply" to ONE short sentence most turns.
- VARY your wording. Do NOT reuse stock phrases turn after turn — never repeat things like "fairly focused", "let's narrow it down", "the strongest fit now is". If you said something last turn, say it differently or not at all.
- BE HELPFUL WITH EXAMPLES, never just a verdict. If the target is broad, do NOT reply with only "that's too broad" — immediately give the user 3-5 concrete example role families pulled from the live data (translated into {lang}) and offer them as the choices. Always pair "that's broad" with real examples they can pick.
- If the user ASKS what the options are (e.g. "what are the options?", "give me examples", "like what?", "what can I choose?"), answer in the context of YOUR PREVIOUS QUESTION above — list options for THAT SAME dimension, do not switch dimensions. If your last question was about skills, list concrete real skills for this role (as suggestions); if about region, list real regions from the live data (facet "states"); if about sector, list the real sectors (facet "sector"); if about role family, list real role families (facet "role"); if about seniority, list the seniority levels. Use the live data for facet dimensions; for open dimensions (skills, languages, certs) put the examples in "suggestions". Do NOT deflect with another generic question.
- Just take in what the user said. If their message answered something OTHER than your previous question (e.g. you asked about region, they gave a salary), accept it naturally and move on — never re-ask the old question or act confused.
- SALARY: figures in this market are MONTHLY GROSS (Austria pays ~14 salaries/year). Always work in monthly gross. Do NOT invent annual-budget→monthly conversions or ask about an annual budget unless the user themselves gives an annual figure. If the user asks a clarifying question (e.g. "monthly or annual?", "monthly approximately?"), answer it in one line ("Yes — monthly gross") and immediately suggest a concrete range, using the real market data above when available (e.g. "typically around €3,800–5,200/month for this role — want me to use that?"). The salary benchmark above is a NATIONAL figure for the role — present it as the market rate for the role, do not attribute it to a specific city/region. Never loop or re-ask the same salary question; if they decline a range, just move on.
- Only mention the count when it actually helps the user decide; don't open every message with a number. The count is the size of the role+region pool ONLY (it does NOT reflect skills, salary, seniority or languages), so never claim "N jobs match your spec" and never imply it should shrink when those are added.

Your turn has these parts:
1. "reply": ONE natural sentence (two only if truly needed) acknowledging what you just captured.
2. "next_question": ONE short, concrete question for the single most useful MISSING piece of the spec. Ask about ONE thing only — never a compound "should I X, or is it specific enough to run now?" question. The role axis is a TWO-STEP funnel driven by the live data above: at stage "sectors" the target isn't pinned to a sector — ask which SECTOR (set facet "sector"); at stage "families" one sector is set — ask which ROLE FAMILY within it (set facet "role"); at stage "done" (sector settled or spanning several sectors), do NOT ask about sector/role again — move to a still-empty dimension (region, seniority, must-have skills, salary, availability, languages). Never re-ask a sector/role question as if nothing was chosen — acknowledge what is already picked first. When the spec already has a clear role, region, and at least one more constraint (or the pool is small), set next_question to "" and invite them to run matching in the reply.
3. "facet": which live-data dimension your next_question asks the user to pick from — "sector" if asking which sector/industry, "role" if asking which role family within a chosen sector, "states" if it's about region, or "" if the question isn't a pick from those lists (e.g. asking about skills/salary) or the spec is complete. This drives clickable quick-pick chips, so it MUST match what you asked and the funnel stage above.
4. "options": LEAVE THIS EMPTY ([]) when facet is "sector" or "role" — the system fills those chips for you from the live data, so you must NOT invent them. Only when facet is "states" do you supply the up-to-5 region choices as objects {{"value": "<exact German region copied verbatim from the live data above>", "label": "<that region rendered in {lang}>"}} (copy the value exactly; translate only the label). Use [] for every other facet.
5. "suggestions": 2-4 SHORT tappable quick-reply chips (max ~3 words each, in {lang}) the user can click to answer your next_question instantly. Tailor them to the question:
   - Open free-text dimension (skills, certifications, languages, notes): 2-3 concrete plausible example answers for THIS specific role, PLUS the chip "What are the options?" so they can ask to see more.
   - Seniority: the actual levels — "Junior", "Mid-level", "Senior", "Expert".
   - Salary: when a benchmark is available above, "Use the market rate" and "I'll set my own".
   - Availability: e.g. "Immediately", "Within 3 months".
   Use [] when facet is "sector", "role" or "states" (the options list already covers those) or when there is no next_question. Each suggestion must read as a natural direct answer the user could send.
6. "answer_field": the ONE draft field your next_question asks the user to fill, so their answer is filed correctly — exactly one of: "sector", "roles", "skills", "levels", "states", "languages", "certs", "salary", "availability" (use "roles" when facet is "role"; mirror the facet for sector/states). Use "" only when there is no next_question."""


class GuidedRegionOption(BaseModel):
    """One region quick-pick chip — value is the verbatim German key, label its translation."""
    value: str
    label: str


class GuidedReply(BaseModel):
    """The guide's turn: a reply plus the single next narrowing question and its quick-pick chips.
    `facet`/`answer_field` route the answer; `options` carry region chips, `suggestions` the rest."""
    reply: str
    next_question: str
    facet: str
    answer_field: str
    options: list[GuidedRegionOption]
    suggestions: list[str]
