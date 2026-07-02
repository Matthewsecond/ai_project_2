"""
apify/linkedin.py — LinkedIn profile enrichment via the Apify actor.

Wraps the `harvestapi/linkedin-profile-scraper` actor (id in config.APIFY_LINKEDIN_ACTOR):
give it one or more LinkedIn profile URLs, get back structured profile data. We map that
onto the app's candidate-profile shape (the same shape the CV parser produces) so the rest
of the pipeline — profile card, matching, saving — is unchanged.

The actor input is { "queries": [<url>, …], "profileScraperMode": <mode> }. We call the
run-sync-get-dataset-items endpoint, which runs the actor and blocks until the dataset is
ready, then returns one item per profile. Each item carries its own `linkedinUrl`, so the
order doesn't need to match the input. Field names are camelCase and several sections are
nested objects (location.parsed, experience[].startDate, …) — all the schema knowledge lives
in this module so a future actor swap only touches the mappers below.
"""
import re
import datetime

import requests

from jobs_intelligence_ai import config

_RUN_SYNC = "https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"


def enrich_linkedin(urls, timeout: int = 300) -> list[dict]:
    """Run the actor for one or more LinkedIn URLs → list of raw enrichment items.

    `urls` may be a single URL string or a list of them; they're enriched in one
    actor run. Each returned item carries its own `linkedinUrl`, so order doesn't
    need to match the input.

    Raises RuntimeError if no API key is configured, or on a non-2xx response from Apify.
    """
    token = config.APIFY_API_KEY
    if not token:
        raise RuntimeError("APIFY_API_KEY is not configured")
    if isinstance(urls, str):
        urls = [urls]
    clean = [u.strip() for u in (urls or []) if isinstance(u, str) and u.strip()]
    if not clean:
        return []
    endpoint = _RUN_SYNC.format(actor=config.APIFY_LINKEDIN_ACTOR)
    resp = requests.post(
        endpoint,
        params={"token": token},
        json={"queries": clean, "profileScraperMode": config.APIFY_LINKEDIN_MODE},
        timeout=timeout,
    )
    # Surface Apify's own explanation on failure (memory/usage limits, invalid
    # input, bad token, …) instead of the opaque "400 Client Error for url …",
    # which leaks the token and tells the user nothing actionable.
    if not resp.ok:
        detail = ""
        try:
            detail = (resp.json().get("error") or {}).get("message") or ""
        except Exception:
            detail = ""
        raise RuntimeError(f"Apify error {resp.status_code}: {detail or resp.reason}")
    items = resp.json()
    return items if isinstance(items, list) else []


def error_message(item: dict) -> str:
    """Extract an error message from a failed item (deleted / private / not-found
    profile), handling either a string or a nested {message|error} object. '' if none."""
    if not isinstance(item, dict):
        return ""
    for k in ("errorMessage", "error", "message"):
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, dict):
            m = v.get("message") or v.get("error")
            if m:
                return str(m).strip()
    return ""


# ── Mapping: Apify LinkedIn item → app candidate-profile dict ──────────────────
def _flag(v) -> bool:
    """Truthy check that also handles a stringified bool ("false"/"0"/"no" → False)."""
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes")
    return bool(v)


def _date_text(d) -> str | None:
    """A date on this actor is {month, year, text} (or {text:'Present'}); take `text`."""
    if isinstance(d, dict):
        return (str(d.get("text")).strip() or None) if d.get("text") else None
    return (str(d).strip() or None) if d else None


def _exp_years(experiences: list) -> str:
    """Rough total experience: current year minus the earliest experience start year."""
    years = []
    for e in experiences or []:
        if not isinstance(e, dict):
            continue
        start = e.get("startDate") or {}
        y = start.get("year") if isinstance(start, dict) else None
        if isinstance(y, int):
            years.append(y)
        else:
            m = re.search(r"(19|20)\d{2}", str((_date_text(start) or "")))
            if m:
                years.append(int(m.group()))
    if not years:
        return ""
    span = datetime.date.today().year - min(years)
    return f"{span} years" if span > 0 else ""


def _skills(raw) -> list[str]:
    """Skills are {name, positions?} objects (occasionally plain strings)."""
    out = []
    for s in raw or []:
        if isinstance(s, str) and s.strip():
            out.append(s.strip())
        elif isinstance(s, dict):
            name = (s.get("name") or "").strip()
            if name:
                out.append(name)
    return out


def _languages(raw) -> str:
    """Languages are {name, proficiency} objects; render "Name (proficiency)"."""
    out = []
    for l in raw or []:
        if isinstance(l, str) and l.strip():
            out.append(l.strip())
        elif isinstance(l, dict):
            name = (l.get("name") or l.get("language") or "").strip()
            if not name:
                continue
            prof = (l.get("proficiency") or "").strip()
            out.append(f"{name} ({prof})" if prof else name)
    return ", ".join(out)


def _experiences(raw) -> list[dict]:
    """Normalise the work-history entries to a compact, display-ready shape.

    Each entry: { title, company, company_url, starts_at, ends_at, description }.
    This is the candidate's prior employers — the most useful enrichment for a
    recruiter — so we keep it structured rather than flattening to text."""
    out = []
    for e in raw or []:
        if not isinstance(e, dict):
            continue
        title   = (e.get("position") or "").strip()
        company = (e.get("companyName") or "").strip()
        if not (title or company):
            continue
        out.append({
            "title":       title,
            "company":     company,
            "company_url": (e.get("companyLinkedinUrl") or "").strip() or None,
            "starts_at":   _date_text(e.get("startDate")),
            "ends_at":     _date_text(e.get("endDate")),
            "description": (e.get("description") or "").strip() or None,
        })
    return out


def _education(raw) -> list[dict]:
    """Normalise education entries: { school, degree, field, starts_at, ends_at }."""
    out = []
    for e in raw or []:
        if not isinstance(e, dict):
            continue
        school = (e.get("schoolName") or "").strip()
        degree = (e.get("degree") or "").strip()
        if not (school or degree):
            continue
        out.append({
            "school":    school,
            "degree":    degree or None,
            "field":     (e.get("fieldOfStudy") or "").strip() or None,
            "starts_at": _date_text(e.get("startDate")),
            "ends_at":   _date_text(e.get("endDate")),
        })
    return out


def _certifications(raw) -> list[str]:
    """Certifications are {title, issuedBy, …} objects (occasionally plain strings)."""
    out = []
    for c in raw or []:
        if isinstance(c, str) and c.strip():
            out.append(c.strip())
        elif isinstance(c, dict):
            name = (c.get("title") or c.get("name") or "").strip()
            if name:
                out.append(name)
    return out


def _title(item: dict) -> str:
    """Prefer the current role (currentPosition / first experience) over the headline."""
    for key in ("currentPosition", "experience"):
        arr = item.get(key) or []
        if arr and isinstance(arr[0], dict):
            pos = (arr[0].get("position") or "").strip()
            co  = (arr[0].get("companyName") or "").strip()
            if pos and co:
                return f"{pos} at {co}"
            if pos or co:
                return pos or co
    return (item.get("headline") or "").strip()


def _follower_count(item: dict):
    fc = item.get("followerCount")
    try:
        return int(fc) if fc is not None else None
    except (TypeError, ValueError):
        return None


def _current_company(item: dict) -> dict | None:
    """Current employer block from currentPosition[0] (no extra request needed).
    This actor doesn't expose industry/size/website, so those stay null."""
    cur = item.get("currentPosition") or []
    if not (cur and isinstance(cur[0], dict)):
        return None
    c = cur[0]
    name = (c.get("companyName") or "").strip()
    if not name:
        return None
    return {
        "name":        name,
        "linkedin_url": (c.get("companyLinkedinUrl") or "").strip() or None,
        "industry":    None,
        "size":        None,
        "website":     None,
    }


def _first_contact(raw) -> str:
    """First usable value from a contact list. Entries may be plain strings or
    {email|number|value: ...} objects."""
    for v in raw or []:
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, dict):
            for key in ("email", "number", "value", "phone"):
                if v.get(key):
                    return str(v[key]).strip()
    return ""


def _email(item: dict) -> str:
    """Best-effort email (only populated in the actor's "+ email search" mode)."""
    for key in ("email", "workEmail", "professionalEmail"):
        v = item.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return _first_contact(item.get("emails"))


def _location(item: dict) -> str:
    """Location = "City, Country" from location.parsed, else the raw linkedinText."""
    loc = item.get("location") or {}
    if not isinstance(loc, dict):
        return str(loc).strip()
    parsed = loc.get("parsed") or {}
    city_country = ", ".join(p for p in (parsed.get("city"), parsed.get("country")) if p)
    return city_country or (loc.get("linkedinText") or "").strip()


def map_to_profile(item: dict) -> dict:
    """Map a raw enrichment item to the candidate-profile shape used app-wide.

    Beyond the headline fields, we retain the structured work history (experiences),
    education, certifications and a few profile signals (headline, avatar, follower
    count, handle) so recruiters keep the full LinkedIn context — especially the
    candidate's prior employers."""
    name = " ".join(p for p in ((item.get("firstName") or "").strip(),
                                (item.get("lastName") or "").strip()) if p) \
        or (item.get("full_name") or item.get("name") or "").strip()
    pic = (item.get("photo") or "").strip() \
        or ((item.get("profilePicture") or {}).get("url") or "").strip()
    return {
        "name":               name,
        "title":              _title(item),
        "headline":           (item.get("headline") or "").strip(),
        "skills":             _skills(item.get("skills")),
        "location":           _location(item),
        "languages":          _languages(item.get("languages")),
        "experience_years":   _exp_years(item.get("experience")),
        "experiences":        _experiences(item.get("experience")),
        "education":          _education(item.get("education")),
        "certifications":     _certifications(item.get("certifications")),
        "email":              _email(item),
        "phone":              "",  # this actor doesn't expose phone numbers
        "salary_expectation": "",  # LinkedIn doesn't expose this
        "availability":       "Open to work" if _flag(item.get("openToWork")) else "",
        "summary":            (item.get("about") or item.get("headline") or "").strip(),
        "linkedin":           (item.get("linkedinUrl") or "").strip(),
        "profile_pic_url":    pic,
        "follower_count":     _follower_count(item),
        "public_identifier":  (item.get("publicIdentifier") or "").strip(),
        # Current employer — used by the "Save companies" button.
        "current_company":    _current_company(item),
        "source":             "imported",   # candidate origin (DB `source` enum)
    }


def to_candidate_text(profile: dict) -> str:
    """A plain-text CV-like blob for the matcher (it embeds candidate_text, not the
    structured profile). Built from the normalized profile so LinkedIn imports match
    like CVs — and so it stays decoupled from the raw actor schema."""
    p = profile or {}
    lines = []
    if p.get("name"):
        lines.append(p["name"])
    if p.get("headline"):
        lines.append(p["headline"])
    if p.get("location"):
        lines.append(f"Location: {p['location']}")
    if p.get("experience_years"):
        lines.append(f"Experience: {p['experience_years']}")
    if p.get("summary"):
        lines.append(f"\nSummary:\n{p['summary']}")

    exps = p.get("experiences") or []
    if exps:
        lines.append("\nExperience:")
        for e in exps:
            span = " ".join(x for x in (e.get("starts_at"), "–" if e.get("ends_at") else "",
                                        e.get("ends_at")) if x)
            lines.append(f"- {e.get('title','')} at {e.get('company','')} ({span})".strip())

    edu = p.get("education") or []
    if edu:
        lines.append("\nEducation:")
        for e in edu:
            lines.append(f"- {e.get('degree','')} — {e.get('school','')}".strip(" —"))

    if p.get("skills"):
        lines.append("\nSkills: " + ", ".join(p["skills"]))
    if p.get("languages"):
        lines.append("Languages: " + p["languages"])
    if p.get("certifications"):
        lines.append("Certifications: " + ", ".join(p["certifications"]))
    return "\n".join(lines).strip()
