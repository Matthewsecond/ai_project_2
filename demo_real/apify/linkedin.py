"""
apify/linkedin.py — LinkedIn profile enrichment via the Apify actor.

Wraps the `anchor/linkedin-profile-enrichment` actor (id in config.APIFY_LINKEDIN_ACTOR):
give it a LinkedIn profile URL, get back structured profile data. We then map that
onto the app's candidate-profile shape (the same shape the CV parser produces) so
the rest of the pipeline — profile card, matching, saving — is unchanged.

The actor input is { "startUrls": [{ "url": <url>, "id": <ref> }] }. We call the
run-sync-get-dataset-items endpoint, which runs the actor and blocks until the
dataset is ready, then returns the items.
"""
import re
import datetime

import requests

import config

_RUN_SYNC = "https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"


def enrich_linkedin(urls, timeout: int = 300) -> list[dict]:
    """Run the actor for one or more LinkedIn URLs → list of raw enrichment items.

    `urls` may be a single URL string or a list of them; they're enriched in one
    actor run (one start fee, one event per profile). Each returned item carries
    its own `url`, so order doesn't need to match the input.

    Raises RuntimeError if no API key is configured, or requests.HTTPError on a
    non-2xx response from Apify.
    """
    token = config.APIFY_API_KEY
    if not token:
        raise RuntimeError("APIFY_API_KEY is not configured")
    if isinstance(urls, str):
        urls = [urls]
    clean = [u.strip() for u in (urls or []) if isinstance(u, str) and u.strip()]
    if not clean:
        return []
    start_urls = [{"url": u, "id": str(i + 1)} for i, u in enumerate(clean)]
    endpoint = _RUN_SYNC.format(actor=config.APIFY_LINKEDIN_ACTOR)
    resp = requests.post(
        endpoint,
        params={"token": token},
        json={"startUrls": start_urls},
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


# ── Mapping: Apify LinkedIn item → app candidate-profile dict ──────────────────
def _exp_years(experiences: list) -> str:
    """Rough total experience: current year minus the earliest experience start."""
    years = []
    for e in experiences or []:
        m = re.search(r"(19|20)\d{2}", str(e.get("starts_at") or ""))
        if m:
            years.append(int(m.group()))
    if not years:
        return ""
    span = datetime.date.today().year - min(years)
    return f"{span} years" if span > 0 else ""


def _languages(raw) -> str:
    """Languages may be strings or {name: ...} objects; join to a readable string."""
    out = []
    for l in raw or []:
        if isinstance(l, str):
            out.append(l)
        elif isinstance(l, dict):
            name = l.get("name") or l.get("language") or ""
            if name:
                out.append(name)
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
        title   = (e.get("title") or "").strip()
        company = (e.get("company") or "").strip()
        if not (title or company):
            continue
        out.append({
            "title":       title,
            "company":     company,
            "company_url": (e.get("company_linkedin_profile_url") or "").strip() or None,
            "starts_at":   (str(e.get("starts_at")).strip() if e.get("starts_at") else None),
            "ends_at":     (str(e.get("ends_at")).strip() if e.get("ends_at") else None),
            "description": (e.get("description") or "").strip() or None,
        })
    return out


def _education(raw) -> list[dict]:
    """Normalise education entries: { school, degree, field, starts_at, ends_at }."""
    out = []
    for e in raw or []:
        if not isinstance(e, dict):
            continue
        school = (e.get("school") or "").strip()
        degree = (e.get("degree_name") or e.get("degree") or "").strip()
        if not (school or degree):
            continue
        out.append({
            "school":    school,
            "degree":    degree or None,
            "field":     (e.get("field_of_study") or "").strip() or None,
            "starts_at": (str(e.get("starts_at")).strip() if e.get("starts_at") else None),
            "ends_at":   (str(e.get("ends_at")).strip() if e.get("ends_at") else None),
        })
    return out


def _certifications(raw) -> list[str]:
    """Certifications may be strings or {name: ...} objects; keep readable names."""
    out = []
    for c in raw or []:
        if isinstance(c, str) and c.strip():
            out.append(c.strip())
        elif isinstance(c, dict):
            name = (c.get("name") or c.get("title") or "").strip()
            if name:
                out.append(name)
    return out


def _title(item: dict) -> str:
    """Prefer the current role (first experience) over the raw headline."""
    exps = item.get("experiences") or []
    if exps:
        e0 = exps[0]
        title, company = (e0.get("title") or "").strip(), (e0.get("company") or "").strip()
        if title and company:
            return f"{title} at {company}"
        if title or company:
            return title or company
    return (item.get("headline") or "").strip()


def _follower_count(item: dict):
    fc = item.get("follower_count")
    try:
        return int(fc) if fc is not None else None
    except (TypeError, ValueError):
        return None


def _current_company(item: dict) -> dict | None:
    """Current employer block from the person scrape (no extra request needed)."""
    name = (item.get("company_name") or "").strip()
    if not name:
        return None
    return {
        "name":        name,
        "linkedin_url": (item.get("company_linkedin") or "").strip() or None,
        "industry":    (item.get("company_industry") or "").strip() or None,
        "size":        (item.get("company_size") or "").strip() or None,
        "website":     (item.get("company_website") or "").strip() or None,
    }


def _first_contact(raw) -> str:
    """First usable value from a contact list (personal_emails / personal_numbers).
    Entries may be plain strings or {email|number|value: ...} objects."""
    for v in raw or []:
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, dict):
            for key in ("email", "number", "value", "phone"):
                if v.get(key):
                    return str(v[key]).strip()
    return ""


def map_to_profile(item: dict) -> dict:
    """Map a raw enrichment item to the candidate-profile shape used app-wide.

    Beyond the headline fields, we now retain the structured work history
    (experiences), education, certifications and a few profile signals
    (headline, avatar, follower count, handle) so recruiters keep the full
    LinkedIn context — especially the candidate's prior employers."""
    location = ", ".join(p for p in (item.get("city"), item.get("country")) if p)
    return {
        "name":               (item.get("full_name") or "").strip(),
        "title":              _title(item),
        "headline":           (item.get("headline") or "").strip(),
        "skills":             [s for s in (item.get("skills") or []) if s],
        "location":           location,
        "languages":          _languages(item.get("languages")),
        "experience_years":   _exp_years(item.get("experiences")),
        "experiences":        _experiences(item.get("experiences")),
        "education":          _education(item.get("education")),
        "certifications":     _certifications(item.get("certifications")),
        "email":              _first_contact(item.get("personal_emails")),
        "phone":              _first_contact(item.get("personal_numbers")),
        "salary_expectation": "",  # LinkedIn doesn't expose this
        "availability":       "Open to work" if item.get("open_to_work") else "",
        "summary":            (item.get("summary") or item.get("headline") or "").strip(),
        "linkedin":           (item.get("url") or "").strip(),
        "profile_pic_url":    (item.get("profile_pic_url") or "").strip(),
        "follower_count":     _follower_count(item),
        "public_identifier":  (item.get("public_identifier") or "").strip(),
        # Current employer with the extra metadata the person scrape already
        # carries (industry/size/website) — used by the "Save companies" button.
        "current_company":    _current_company(item),
        "source":             "imported",   # candidate origin (DB `source` enum)
    }


def to_candidate_text(item: dict, profile: dict) -> str:
    """A plain-text CV-like blob for the matcher (it embeds candidate_text, not the
    structured profile). Built from the enrichment so LinkedIn imports match like CVs."""
    lines = []
    if profile.get("name"):
        lines.append(profile["name"])
    if item.get("headline"):
        lines.append(item["headline"])
    if profile.get("location"):
        lines.append(f"Location: {profile['location']}")
    if profile.get("experience_years"):
        lines.append(f"Experience: {profile['experience_years']}")
    if profile.get("summary"):
        lines.append(f"\nSummary:\n{profile['summary']}")

    exps = item.get("experiences") or []
    if exps:
        lines.append("\nExperience:")
        for e in exps:
            span = " ".join(x for x in (e.get("starts_at"), "–" if e.get("ends_at") else "",
                                        e.get("ends_at")) if x)
            lines.append(f"- {e.get('title','')} at {e.get('company','')} ({span})".strip())

    edu = item.get("education") or []
    if edu:
        lines.append("\nEducation:")
        for e in edu:
            lines.append(f"- {e.get('degree_name','')} — {e.get('school','')}".strip(" —"))

    if profile.get("skills"):
        lines.append("\nSkills: " + ", ".join(profile["skills"]))
    if profile.get("languages"):
        lines.append("Languages: " + profile["languages"])
    certs = [c for c in (item.get("certifications") or []) if c]
    if certs:
        lines.append("Certifications: " + ", ".join(
            c if isinstance(c, str) else c.get("name", "") for c in certs))
    return "\n".join(lines).strip()
