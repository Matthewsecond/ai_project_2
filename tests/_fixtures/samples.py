"""
Sample data for unit tests — deterministic, no network, no DB.

Job rows are expressed as LOGICAL keys (the keys of config.COL), not raw DB column
names, so a test can map them through the active country's COL:

    row = {col[k]: v for k, v in SAMPLE_JOB_VALUES.items() if k in col}

LLM response samples cover the formats the parsers must tolerate.
"""

# ── Candidate CV ────────────────────────────────────────────────────────────────
SAMPLE_CV = (
    "Senior Python engineer, 8 years, Vienna. Django, FastAPI, PostgreSQL, AWS. "
    "Led a team of 4. Open to hybrid roles, available from August."
)

# ── Job row (logical keys → values; map through config.COL in the test) ──────────
SAMPLE_JOB_VALUES = {
    "job_id":      "1166922",
    "title":       "Key Account Manager",
    "company":     "CoolPeople s. r. o.",
    "state":       "Bratislavský kraj",
    "city":        "Bratislava",
    "salary":      "3500",
    "url":         "https://example.com/jobs/1166922",
    "portal":      "profesia.sk",
    "occ_group":   "Sales",
    "date_posted": "2026-06-01",
    "description": "Manage key accounts and grow revenue in the BA region.",
}

# ── LLM response samples (for the JSON extractors) ───────────────────────────────
# parse_json (array shape) ----------------------------------------------------------
LLM_ARRAY_FENCED = '```json\n[12345, 67890]\n```'
LLM_ARRAY_BARE = '[12345, 67890]'
LLM_ARRAY_WITH_PROSE = 'Here are the ids:\n[12345, 67890]\nThanks.'

# _parse (object with "jobs") --------------------------------------------------------
LLM_JOBS_FENCED = (
    'Found 2 roles.\n'
    '```json\n{"jobs":[{"job_id":"1","title":"Engineer"},{"job_id":"2","title":"Analyst"}]}\n```'
)
LLM_JOBS_BARE = '{"jobs":[{"job_id":"1","title":"Engineer"}]}'

# _parse_candidate (object with "profile_updates") -----------------------------------
LLM_PROFILE_FENCED = (
    'Added the licence.\n'
    '```json\n{"profile_updates":{"skills":["forklift"]},"cv_note":"Holds a forklift licence."}\n```'
)

# Citation markers: OpenAI file_search annotates with private-use-area chars
# (U+E200 start … U+E201 end). parse_json must strip them from string values.
_CITE_START, _CITE_END = chr(0xE200), chr(0xE201)
LLM_ARRAY_WITH_CITATIONS = (
    '[{"title":"Engineer' + _CITE_START + 'filecite turn0file6' + _CITE_END + '"}]'
)
