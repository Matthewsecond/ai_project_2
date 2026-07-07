"""
utils.py — Pure helpers for the search module (no state, no OpenAI client).

  parse_json     : pull a JSON array out of a model response (citation-marker safe)
  passes_filters : hard-filter a DB row against the request filters
  serialize_job  : turn a raw DB row into the flat job dict the API returns
"""
import datetime as _dt
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


def nace_levels(code: str | None) -> tuple[str | None, str | None, str | None]:
    """Split a raw NACE/industry code into 3 cascading levels.

    AT codes are dot-separated (e.g. "25.12.0" -> division "25", group "25.12",
    class "25.12.0"). SK codes are plain digit strings (e.g. "62100" -> division
    "62", group "621", class "62100"). Either way callers only see 3 levels."""
    if not code:
        return (None, None, None)
    code = str(code).strip()
    if "." in code:
        parts = code.split(".")
        lvl1 = parts[0] or None
        lvl2 = ".".join(parts[:2]) if len(parts) >= 2 else None
        lvl3 = code if len(parts) >= 3 else None
        return (lvl1, lvl2, lvl3)
    lvl1 = code[:2] or None
    lvl2 = code[:3] if len(code) >= 3 else None
    lvl3 = code if len(code) >= 5 else None
    return (lvl1, lvl2, lvl3)


def _parse_salary_num(raw) -> float | None:
    """Best-effort extraction of a representative monthly number from a free-text
    salary string (e.g. "€3,000 - €4,000/month" -> 3000.0). Used for range
    filtering only — display formatting elsewhere is unaffected."""
    if raw is None:
        return None
    m = re.search(r"[\d.,]+", str(raw).replace(" ", ""))
    if not m:
        return None
    num = m.group().replace(".", "").replace(",", "") if "," in m.group() and "." in m.group() \
        else m.group().replace(",", ".")
    try:
        return float(num)
    except ValueError:
        return None


def _within_days(date_val, days: int) -> bool:
    """True if date_val (date/datetime/str) is within the last `days` days."""
    if not date_val:
        return False
    if isinstance(date_val, str):
        try:
            date_val = _dt.datetime.fromisoformat(date_val[:19])
        except ValueError:
            return False
    d = date_val.date() if isinstance(date_val, _dt.datetime) else date_val
    return (_dt.date.today() - d).days <= days


def passes_filters(row: dict, filters: dict) -> bool:
    c = config.COL
    if filters.get("state") and row.get(c["state"]) != filters["state"]:
        return False
    if filters.get("portal") and row.get(c["portal"]) != filters["portal"]:
        return False
    if filters.get("occ_group") and row.get(c["occ_group"]) != filters["occ_group"]:
        return False
    if filters.get("work_time") and row.get(c["work_time"]) != filters["work_time"]:
        return False
    if (filters.get("employment_relationship")
            and row.get(c["employment_relationship"]) != filters["employment_relationship"]):
        return False
    if filters.get("education") and row.get(c["education"]) != filters["education"]:
        return False
    if filters.get("city"):
        city_val = str(row.get(c["city"], "") or "")
        if filters["city"].lower() not in city_val.lower():
            return False

    # Job Status
    if filters.get("status") and row.get(c["status"]) != filters["status"]:
        return False
    if filters.get("online_since") and not _within_days(row.get(c["date_posted"]), int(filters["online_since"])):
        return False
    if filters.get("scraping_date") and not _within_days(row.get("updated_at"), int(filters["scraping_date"])):
        return False
    if filters.get("available_from"):
        start_val = str(row.get(c.get("start_timeline", "start_timeline"), "") or "")
        if filters["available_from"].lower() not in start_val.lower():
            return False

    # Region
    if filters.get("postcode") and config.PROFILE.col_present("zipcode"):
        zip_val = str(row.get(c.get("zipcode", "zipcode"), "") or "")
        if not zip_val.startswith(filters["postcode"]):
            return False

    # Job Criteria
    if filters.get("job_description"):
        desc_val = str(row.get("_scraped_description") or row.get(c["description"], "") or "")
        if filters["job_description"].lower() not in desc_val.lower():
            return False
    if filters.get("skills"):
        skills_val = " ".join([
            str(row.get(c.get("skills", "skills"), "") or ""),
            str(row.get(c.get("skills_en", "skills_english"), "") or ""),
        ]).lower()
        terms = [t.strip().lower() for t in filters["skills"].split(",") if t.strip()]
        if terms and not any(t in skills_val for t in terms):
            return False
    if filters.get("salary_min") or filters.get("salary_max"):
        num = _parse_salary_num(row.get(c["salary"]))
        if num is None:
            return False
        if filters.get("salary_min") and num < float(filters["salary_min"]):
            return False
        if filters.get("salary_max") and num > float(filters["salary_max"]):
            return False

    # Company Criteria
    if filters.get("company"):
        company_val = str(row.get(c["company"], "") or "")
        if filters["company"].lower() not in company_val.lower():
            return False
    if filters.get("nace1") or filters.get("nace2") or filters.get("nace3"):
        lvl1, lvl2, lvl3 = nace_levels(row.get("_nace_code"))
        if filters.get("nace1") and lvl1 != filters["nace1"]:
            return False
        if filters.get("nace2") and lvl2 != filters["nace2"]:
            return False
        if filters.get("nace3") and lvl3 != filters["nace3"]:
            return False
    if filters.get("exclude_staffing") and config.PROFILE.has_staffing_filter:
        if row.get("personal_service_provider"):
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
        # Raw column names (identical across country profiles, unlike most other
        # fields) — fully populated on every row, unlike publication_date/"posted"
        # above (~47% NULL on the SK market).
        "created_at":             _str(job.get("created_at")),
        "updated_at":             _str(job.get("updated_at")),
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
