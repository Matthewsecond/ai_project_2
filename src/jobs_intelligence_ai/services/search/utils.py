"""
utils.py — Pure helpers for the search module (no state, no OpenAI client).

  parse_json     : pull a JSON array out of a model response (citation-marker safe)
  passes_filters : hard-filter a DB row against the request filters
  serialize_job  : turn a raw DB row into the flat job dict the API returns
"""
import json
import re

from jobs_intelligence_ai import config

# OpenAI file_search annotates answers with private-use-area citation markers
# (start U+E200, end U+E201, e.g. "filecite ... turn0file6"). Left in a
# match_reason they garble the UI and crash cp1252 consoles, so we strip them.
# Patterns are built from code points to keep this source file pure ASCII.
_CITE_START, _CITE_END = chr(0xE200), chr(0xE201)
_CITATION_SPAN = re.compile(_CITE_START + "[^" + _CITE_END + "]*" + _CITE_END)
_PUA_CHARS     = re.compile("[" + chr(0xE000) + "-" + chr(0xF8FF) + "]")


def parse_json(text: str) -> list:
    """Extract a JSON array from the model's response, with citation markers
    stripped from any string values it contains."""
    text = re.sub(r"```(?:json)?", "", text or "").strip().rstrip("`").strip()

    data = None
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            data = parsed
    except Exception:
        pass
    if data is None:
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
                if isinstance(parsed, list):
                    data = parsed
            except Exception:
                pass

    return [_clean(item) for item in data] if data is not None else []


def _clean(item):
    """Strip citation markers from the string values of a parsed item.

    Done after json.loads so it catches the markers whether the model emitted them
    as literal characters or as \\uXXXX escapes in the JSON text.
    """
    if isinstance(item, str):
        return _strip_citation_markers(item)
    if isinstance(item, dict):
        return {k: (_strip_citation_markers(v) if isinstance(v, str) else v)
                for k, v in item.items()}
    return item


def _strip_citation_markers(text: str) -> str:
    """Drop file_search citation tokens (and any orphan private-use chars)."""
    return _PUA_CHARS.sub("", _CITATION_SPAN.sub("", text))


def passes_filters(row: dict, filters: dict) -> bool:
    c = config.COL
    if filters.get("state") and row.get(c["state"]) != filters["state"]:
        return False
    if filters.get("portal") and row.get(c["portal"]) != filters["portal"]:
        return False
    if filters.get("occ_group") and row.get(c["occ_group"]) != filters["occ_group"]:
        return False
    if filters.get("city"):
        city_val = str(row.get(c["city"], "") or "")
        if filters["city"].lower() not in city_val.lower():
            return False
    return True


def serialize_job(job: dict) -> dict:
    c = config.COL
    return {
        "job_id":                 _str(job.get(c["job_id"])),
        "title":                  _str(job.get(c["title"])) or "Untitled",
        "company":                _str(job.get(c["company"])) or "Unknown",
        "state":                  _str(job.get(c["state"])),
        "city":                   _str(job.get(c["city"])),
        "municipality":           _str(job.get(c.get("municipality", "municipality"))),
        "zipcode":                _str(job.get(c.get("zipcode", "zipcode"))),
        "detailed_location":      _str(job.get(c.get("detailed_location", "detailed_location"))),
        "salary":                 _str(job.get(c["salary"])),
        "salary_type":            _str(job.get(c.get("salary_type", "salary_type"))),
        "original_salary":        _str(job.get(c.get("original_salary", "original_salary"))),
        "work_time":              _str(job.get(c.get("work_time", "work_time"))),
        "employment_relationship":_str(job.get(c.get("employment_relationship", "employment_relationship"))),
        "education":              _str(job.get(c.get("education", "education"))),
        "url":                    _str(job.get(c["url"])),
        "portal":                 _str(job.get(c["portal"])),
        "order_number":           _str(job.get(c.get("order_number", "order_number"))),
        "occ_group":              _str(job.get(c["occ_group"])),
        "posted":                 _str(job.get(c["date_posted"])),
        "application_deadline":   _str(job.get(c.get("application_deadline", "application_deadline"))),
        "start_timeline":         _str(job.get(c.get("start_timeline", "start_timeline"))),
        # The scraped full text when the fetch attached one (SK — see
        # _add_scraped_descriptions), else the read view's description/summary column.
        "description":            _str(job.get("_scraped_description")) or _str(job.get(c["description"])),
        "summary":                _str(job.get(c.get("summary", "summary"))),
        "skills":                 _str(job.get(c.get("skills", "skills"))),
        "skills_en":              _str(job.get(c.get("skills_en", "skills_english"))),
        "contacts":               _str(job.get(c.get("contacts", "contacts"))) or _compose_contacts(job),
        "lat":                    job.get("_lat"),
        "lon":                    job.get("_lon"),
    }


def _str(val) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def _compose_contacts(job: dict) -> str | None:
    """Build a contacts string from the split contact_name/mail/phone columns.

    View_Jobs_Test exposes recruiter contact info as three columns instead of the
    single `contacts` field View_Jobs_Full has; recompose them so the job-detail
    view still shows contact info. Returns None when no parts are present.
    """
    parts = [job.get("contact_name"), job.get("contact_mail"), job.get("contact_phone")]
    parts = [str(p).strip() for p in parts if p and str(p).strip()]
    return " · ".join(parts) if parts else None
