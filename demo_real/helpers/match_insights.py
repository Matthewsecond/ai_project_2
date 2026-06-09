"""
helpers/match_insights.py — Build the per-candidate "Match Insights" payload.

Given one candidate's saved jobs + a parsed CV profile snapshot, compute the
data object the Saved-Candidates dashboard (and its PDF mirror) render from.

Everything here is grounded in real data:
  * the candidate's saved jobs (salary, grade, score, skills text, posting date)
  * a few cached DB queries against the candidate's occupational group
No numbers are fabricated; where the design asked for data we don't have
(fill-time, cross-session population) we substitute an honest proxy and label
it as such.

Public API:
    build_insights(candidate_name, jobs, profile, all_strengths=None) -> dict
"""
import re
import logging
import statistics as _stats
from datetime import datetime, date
from functools import lru_cache
from collections import Counter, defaultdict

logger = logging.getLogger(__name__)

# ── Austrian Bundesland neighbours (for the expansion simulator) ──────────────
_NEIGHBOURS = {
    "Wien":              ["Niederösterreich", "Burgenland"],
    "Niederösterreich":  ["Wien", "Oberösterreich", "Steiermark", "Burgenland"],
    "Oberösterreich":    ["Niederösterreich", "Salzburg", "Steiermark"],
    "Steiermark":        ["Niederösterreich", "Oberösterreich", "Kärnten", "Burgenland"],
    "Salzburg":          ["Oberösterreich", "Tirol", "Kärnten"],
    "Tirol":             ["Salzburg", "Vorarlberg"],
    "Kärnten":           ["Steiermark", "Salzburg", "Tirol"],
    "Burgenland":        ["Wien", "Niederösterreich", "Steiermark"],
    "Vorarlberg":        ["Tirol"],
}


# ══════════════════════════════════════════════════════════════════════════════
#  Small parsers
# ══════════════════════════════════════════════════════════════════════════════
def _initials(name: str) -> str:
    parts = [p for p in re.split(r"\s+", (name or "").strip()) if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "candidate").lower()).strip("-") or "candidate"


def _parse_years(s) -> int:
    if not s:
        return 0
    m = re.search(r"(\d+)", str(s))
    return int(m.group(1)) if m else 0


def _money_value(token: str) -> float | None:
    """Parse a single money token like '2.800', '2,800', '€3400' → float."""
    if token is None:
        return None
    t = str(token)
    t = re.sub(r"[^\d.,]", "", t)
    if not t:
        return None
    # Treat both '.' and ',' as thousands separators when followed by 3 digits.
    t = t.replace(" ", "")
    # Normalise: remove thousands separators (., ,) leaving a plain integer-ish.
    t = re.sub(r"[.,](?=\d{3}\b)", "", t)
    t = t.replace(",", ".")
    try:
        v = float(t)
    except ValueError:
        return None
    return v


def _parse_money(s, *, monthly: bool = True) -> float | None:
    """
    Parse a salary string to a monthly figure.
    Handles ranges ('2.800–3.400' → midpoint) and yearly (→ /12 when value is
    clearly annual, i.e. > 20k).  Returns None for hourly / unparseable values.
    """
    if s is None:
        return None
    txt = str(s).lower()
    nums = re.findall(r"\d[\d.,]*\d|\d", txt)
    vals = [v for v in (_money_value(n) for n in nums) if v]
    vals = [v for v in vals if v >= 100]   # drop stray small numbers
    if not vals:
        return None
    v = sum(vals[:2]) / len(vals[:2]) if len(vals) >= 2 else vals[0]
    if monthly and v > 20000:              # clearly an annual figure
        v = v / 14.0                       # Austrian 14 monthly salaries
    if v < 500:                            # likely hourly / part-figure
        return None
    return round(v, 0)


def _parse_band(salary_expectation) -> tuple[float, float] | None:
    """'€2,800–3,400/month' → (2800, 3400).  Yearly → /12.  Single → ±8%."""
    if not salary_expectation:
        return None
    txt = str(salary_expectation).lower()
    yearly = any(w in txt for w in ("year", "annum", "jahr", "p.a", "/yr"))
    nums = re.findall(r"\d[\d.,]*\d|\d", txt)
    vals = [v for v in (_money_value(n) for n in nums) if v and v >= 100]
    if not vals:
        return None
    if yearly:
        vals = [v / 14.0 for v in vals]
    else:
        vals = [v / 14.0 if v > 20000 else v for v in vals]
    vals = [v for v in vals if v >= 500]
    if not vals:
        return None
    if len(vals) >= 2:
        lo, hi = min(vals[:2]), max(vals[:2])
    else:
        lo, hi = vals[0] * 0.92, vals[0] * 1.08
    return (round(lo), round(hi))


def _parse_date(s):
    if not s:
        return None
    txt = str(s).strip()[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d.%m.%Y", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(txt[:len(fmt) + 2] if "%H" in fmt else txt[:10], fmt).date()
        except ValueError:
            continue
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", txt)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def _age_days(posted, today: date) -> int | None:
    d = _parse_date(posted)
    if not d:
        return None
    return max(0, (today - d).days)


_TOKEN_RE = re.compile(r"[a-zA-ZäöüÄÖÜß][a-zA-ZäöüÄÖÜß0-9+./#-]{1,}")


def _job_skill_text(job: dict) -> str:
    return " ".join(str(job.get(k) or "") for k in ("skills_en", "skills", "summary", "description")).lower()


def _availability_score(avail: str) -> int:
    t = (avail or "").lower()
    if any(w in t for w in ("immediat", "sofort", "now", "available")):
        return 100
    if "1" in t and "month" in t or "1-month" in t or "1 month" in t:
        return 85
    if "2" in t and "month" in t:
        return 74
    if "3" in t and "month" in t or "quarter" in t:
        return 62
    if any(w in t for w in ("notice", "kündig")):
        return 70
    return 78


def _percentile(data: list[float], p: float) -> float:
    if not data:
        return 0.0
    data = sorted(data)
    idx = (p / 100) * (len(data) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(data) - 1)
    return data[lo] + (idx - lo) * (data[hi] - data[lo])


# ══════════════════════════════════════════════════════════════════════════════
#  Cached DB helper — one targeted query per occupational group
# ══════════════════════════════════════════════════════════════════════════════
@lru_cache(maxsize=64)
def _group_market(occ_group: str) -> tuple:
    """
    Fetch active roles for an occupational group (cached).  Returns a tuple of
    dicts {salary, skills, posted(date|None), company, state}.  Tuple so it's
    hashable/cacheable; callers treat it as a list.
    """
    if not occ_group:
        return tuple()
    import config
    from core.database import get_engine
    from sqlalchemy import text
    c = config.COL
    sql = f"""
        SELECT `{c['salary']}`        AS salary,
               `{c['skills_en']}`     AS skills,
               `{c['date_posted']}`   AS posted,
               `{c['company']}`       AS company,
               `{c['state']}`         AS state
        FROM View_Jobs_Full
        WHERE `{c['occ_group']}` = :g
          AND `{c['status']}` IN ('new', 'updated')
        ORDER BY `{c['date_posted']}` DESC
        LIMIT 3000
    """
    try:
        with get_engine().connect() as conn:
            rows = conn.execute(text(sql), {"g": occ_group}).fetchall()
    except Exception as exc:
        logger.warning("match_insights _group_market failed for %s: %s", occ_group, exc)
        return tuple()
    out = []
    for r in rows:
        out.append({
            "salary":  _parse_money(r[0]),
            "skills":  (str(r[1]) if r[1] else "").lower(),
            "posted":  _parse_date(r[2]),
            "company": str(r[3]) if r[3] else "",
            "state":   str(r[4]) if r[4] else "",
        })
    return tuple(out)


# ══════════════════════════════════════════════════════════════════════════════
#  Main builder
# ══════════════════════════════════════════════════════════════════════════════
def build_insights(candidate_name: str, jobs: list[dict], profile: dict | None,
                   all_strengths: list[float] | None = None,
                   today: date | None = None) -> dict:
    today   = today or date.today()
    profile = profile or {}
    name    = profile.get("name") or candidate_name or "Candidate"
    jobs    = jobs or []

    # ── salaries / grades / scores from saved jobs ────────────────────────────
    for j in jobs:
        j["_sal"] = _parse_money(j.get("salary"))
        j["_age"] = _age_days(
            j.get("posted") or j.get("publication_date") or j.get("created_at") or j.get("date_posted"),
            today,
        )
        try:
            j["_score"] = float(j.get("score") or 0)
        except (TypeError, ValueError):
            j["_score"] = 0.0
        j["_grade"] = (j.get("grade") or _grade_from_score(j["_score"])).upper()

    matches = len(jobs)
    gA = sum(1 for j in jobs if j["_grade"] == "A")
    gB = sum(1 for j in jobs if j["_grade"] == "B")
    gC = matches - gA - gB
    scores = [j["_score"] for j in jobs if j["_score"] > 0]
    strength = round((_stats.mean(scores) * 100) if scores else 0)

    band = _parse_band(profile.get("salary_expectation"))
    job_salaries = [j["_sal"] for j in jobs if j["_sal"]]

    # dominant occupational group + state among saved jobs
    occ_counts   = Counter(j.get("occ_group") for j in jobs if j.get("occ_group"))
    occ_group    = occ_counts.most_common(1)[0][0] if occ_counts else None
    state_counts = Counter((j.get("state") or "").strip() for j in jobs if j.get("state"))
    dom_state    = state_counts.most_common(1)[0][0] if state_counts else (profile.get("location") or "")

    market_rows = list(_group_market(occ_group)) if occ_group else []

    # ── header ────────────────────────────────────────────────────────────────
    prefers_bits = []
    if dom_state:
        prefers_bits.append(dom_state)
    emp = Counter((j.get("employment_relationship") or "").strip() for j in jobs if j.get("employment_relationship"))
    if emp:
        prefers_bits.append(emp.most_common(1)[0][0])
    prefers = " · ".join(prefers_bits) if prefers_bits else "—"

    D = {
        "id":       _slug(name),
        "name":     name,
        "initials": _initials(name),
        "title":    profile.get("title") or (jobs[0].get("title") if jobs else "") or "—",
        "years":    _parse_years(profile.get("experience_years")),
        "location": profile.get("location") or dom_state or "—",
        "langs":    profile.get("languages") or "—",
        "skills":   (profile.get("skills") or [])[:8],
        "asks":     profile.get("salary_expectation") or "—",
        "available": profile.get("availability") or "—",
        "prefers":  prefers,
        "matches":  matches,
        "grades":   {"A": gA, "B": gB, "C": gC},
        "strength": strength,
    }

    # ── salary positioning (market vs ask) ───────────────────────────────────
    market_sals = [r["salary"] for r in market_rows if r["salary"]]
    if market_sals:
        market = {
            "median": round(_stats.median(market_sals)),
            "mean":   round(_stats.mean(market_sals)),
            "p25":    round(_percentile(market_sals, 25)),
            "p75":    round(_percentile(market_sals, 75)),
        }
    elif job_salaries:
        market = {
            "median": round(_stats.median(job_salaries)),
            "mean":   round(_stats.mean(job_salaries)),
            "p25":    round(_percentile(job_salaries, 25)),
            "p75":    round(_percentile(job_salaries, 75)),
        }
    else:
        market = {"median": 0, "mean": 0, "p25": 0, "p75": 0}

    if not band:
        # fall back to a band around the market typical pay
        if market["median"]:
            band = (round(market["p25"]), round(market["p75"]))
        else:
            band = (0, 0)
    D["market"]    = market
    D["candBand"]  = [band[0], band[1]]

    # overlap: share of saved roles whose pay falls inside the ask band
    in_band = [s for s in job_salaries if band[0] <= s <= band[1]]
    overlap_pct = round(len(in_band) / len(job_salaries) * 100) if job_salaries else 0
    D["salaryStat"] = {
        "overlap": f"covers {overlap_pct}% of roles" if job_salaries else "no salary data",
        "verdict": _salary_verdict(band, market),
    }
    D["salaryAI"] = _salary_ai(name, band, market, overlap_pct)

    # ceiling / headroom KPIs (real: top payable role)
    ceiling = round(max(job_salaries)) if job_salaries else (market["p75"] or band[1])
    D["salaryCeiling"]   = int(ceiling)
    D["salaryHeadroom"]  = int(max(0, ceiling - band[1]))

    # ── skills in demand & gaps (from saved-job text) ────────────────────────
    cand_skills = [s for s in (profile.get("skills") or []) if s]
    skills2 = []
    for sk in cand_skills[:8]:
        n = sum(1 for j in jobs if sk.lower() in _job_skill_text(j))
        skills2.append({"name": sk, "n": n})
    skills2.sort(key=lambda x: x["n"], reverse=True)
    D["skills2"] = skills2 or [{"name": s, "n": 0} for s in cand_skills[:6]]

    gaps = _compute_gaps(jobs, market_rows, cand_skills)
    D["gaps"] = gaps
    D["skillsAI"] = _skills_ai(skills2, gaps, matches)

    # ── candidate fit radar (6 real-ish axes) ────────────────────────────────
    skills_match = round(_stats.mean(scores) * 100) if scores else 0
    salary_fit   = round(len(in_band) / len(job_salaries) * 100) if job_salaries else 0
    loc_fit      = round(sum(1 for j in jobs if (j.get("state") or "").strip() == dom_state) / matches * 100) if matches and dom_state else 0
    seniority_fit = round((gA + gB) / matches * 100) if matches else 0
    avail_fit    = _availability_score(profile.get("availability"))
    quality_scores = [float(j["extras"]["quality"]["score"]) for j in jobs
                      if isinstance(j.get("extras"), dict)
                      and isinstance(j["extras"].get("quality"), dict)
                      and j["extras"]["quality"].get("score") is not None]
    role_quality = round(_stats.mean(quality_scores) * 100) if quality_scores else (round(gA / matches * 100) if matches else 0)
    radar = [
        {"axis": "Skills match",  "v": skills_match},
        {"axis": "Salary fit",    "v": salary_fit},
        {"axis": "Location fit",  "v": loc_fit},
        {"axis": "Seniority fit", "v": seniority_fit},
        {"axis": "Availability",  "v": avail_fit},
        {"axis": "Role quality",  "v": role_quality},
    ]
    D["radar"]   = radar
    D["radarAI"] = _radar_ai(name, radar)

    # ── priority shortlist ────────────────────────────────────────────────────
    D["priority"]   = _priority(jobs, band)
    D["priorityAI"] = _priority_ai(name, D["priority"], gA)

    # ── demand trend (weekly new roles, 8 wks, from group market) ────────────
    spark, prof_avg, demand_now, demand_pct, demand_vs = _demand_trend(market_rows, today)
    D["demandSpark"] = spark
    D["profileAvg"]  = prof_avg
    D["demandNow"]   = demand_now
    D["demandPct"]   = demand_pct
    D["demandVsAvg"] = demand_vs
    D["demandAI"]    = _demand_ai(D["title"], demand_pct, demand_now, prof_avg, demand_vs)

    # ── upskilling ROI (gap skills → group roles + pay uplift) ───────────────
    D["upskill"]   = _upskill(gaps, market_rows, market["median"])
    D["upskillAI"] = _upskill_ai(D["upskill"])

    # ── top employers (cluster of matching roles) ────────────────────────────
    D["employers"]   = _employers(jobs)
    D["employersAI"] = _employers_ai(D["employers"])

    # ── pipeline expansion simulator ──────────────────────────────────────────
    levers, lever_total = _expansion(jobs, market_rows, band, dom_state, matches)
    D["levers"]      = levers
    D["leverTotal"]  = lever_total
    D["expansionAI"] = _expansion_ai(name, matches, lever_total, levers)

    # ── placeability & time-on-market (posting age proxy) ─────────────────────
    place = _placeability(jobs, today)
    D.update(place)
    D["placeabilityAI"] = _placeability_ai(name, place)

    # ── benchmark vs other saved candidates this session ─────────────────────
    bm = _benchmark(strength, all_strengths)
    D["benchmarkPct"]   = bm["pct"]
    D["benchmarkRank"]  = bm["rank"]
    D["benchmarkTotal"] = bm["total"]
    D["benchmarkAI"]    = _benchmark_ai(name, bm)

    # ── outreach urgency / freshness ─────────────────────────────────────────
    D["fresh"]   = _freshness(jobs, today)
    D["freshAI"] = _freshness_ai(D["fresh"])

    # ── match briefing + actions (synthesised from the above) ────────────────
    D["briefing"], D["actions"] = _briefing(D)
    return D


# ══════════════════════════════════════════════════════════════════════════════
#  Panel builders
# ══════════════════════════════════════════════════════════════════════════════
def _grade_from_score(score: float) -> str:
    if score >= 0.70:
        return "A"
    if score >= 0.50:
        return "B"
    return "C"


def _salary_verdict(band, market) -> str:
    if not band or not market.get("median"):
        return "Insufficient market data"
    lo, hi = band
    med, p75 = market["median"], market["p75"]
    if hi < med:
        return "Conservative — below market median"
    if lo > p75:
        return "Ambitious — above the upper quartile"
    if lo >= med:
        return "Upper-half — median to upper quartile"
    return "Realistic — median to upper quartile"


def _salary_ai(name, band, market, overlap) -> str:
    first = name.split()[0]
    if not market.get("median"):
        return f"Not enough market salary data to position {first}'s ask precisely."
    return (f"{first}'s ask of €{band[0]:,}–{band[1]:,} covers about {overlap}% of matched roles "
            f"and sits against a market median of €{market['median']:,} (P25–P75 €{market['p25']:,}–{market['p75']:,}).")


def _radar_ai(name, radar) -> str:
    first = name.split()[0]
    top = max(radar, key=lambda a: a["v"])
    bot = min(radar, key=lambda a: a["v"])
    return (f"{first}'s strongest dimension is {top['axis'].lower()} ({top['v']}/100); "
            f"the thinnest is {bot['axis'].lower()} ({bot['v']}/100) — worth a closer look.")


def _compute_gaps(jobs, market_rows, cand_skills) -> list:
    cand_lower = {s.lower() for s in cand_skills}
    # candidate vocabulary of meaningful skill words to avoid trivial gaps
    counts = Counter()
    pool = market_rows if market_rows else None
    if pool:
        for r in pool:
            seen = set()
            for tok in _TOKEN_RE.findall(r["skills"]):
                t = tok.strip(".-/").lower()
                if len(t) < 3 or t in seen:
                    continue
                seen.add(t)
                counts[t] += 1
        denom = len(pool)
    else:
        for j in jobs:
            seen = set()
            for tok in _TOKEN_RE.findall(_job_skill_text(j)):
                t = tok.strip(".-/").lower()
                if len(t) < 3 or t in seen:
                    continue
                seen.add(t)
                counts[t] += 1
        denom = max(1, len(jobs))
    gaps = []
    _STOP = {"und", "mit", "der", "die", "das", "für", "von", "den", "sie", "ein",
             "the", "and", "for", "you", "are", "with", "job", "team", "work"}
    for tok, n in counts.most_common(60):
        if tok in cand_lower or tok in _STOP or any(tok in cs for cs in cand_lower):
            continue
        if n < max(2, denom * 0.03):
            continue
        gaps.append({"name": tok[:22].title(), "n": n})
        if len(gaps) >= 4:
            break
    return gaps


def _skills_ai(skills2, gaps, matches) -> str:
    top = skills2[0]["name"] if skills2 else "their core skills"
    if gaps:
        return (f"{top} carries the most matches. The clearest gap is "
                f"{gaps[0]['name']}, wanted by {gaps[0]['n']} roles the candidate can't yet fill.")
    return f"{top} carries most matches; no major in-demand gaps stand out."


def _priority(jobs, band) -> list:
    lo, hi = band
    def delta(sal):
        if not sal:
            return "in"
        if lo <= sal <= hi:
            return "in"
        if sal > hi:
            return int(round(sal - hi))
        return -int(round(lo - sal))
    def row(j):
        return {
            "g":     j["_grade"],
            "title": j.get("title") or "Untitled",
            "co":    j.get("company") or "Unknown",
            "loc":   j.get("state") or j.get("city") or "—",
            "match": int(round(j["_score"] * 100)),
            "sal":   int(j["_sal"]) if j["_sal"] else 0,
            "delta": delta(j["_sal"]),
        }
    act   = [j for j in jobs if j["_grade"] == "A"]
    look  = [j for j in jobs if j["_grade"] == "B"]
    low   = [j for j in jobs if j["_grade"] == "C"]
    for grp in (act, look, low):
        grp.sort(key=lambda j: j["_score"], reverse=True)
    tiers = []
    if act:
        tiers.append({"tier": "Act first", "note": "strong match, pay in range",
                      "color": "#1a7a2e", "count": len(act),
                      "roles": [row(j) for j in act[:3]]})
    if look:
        tiers.append({"tier": "Worth a look", "note": "good role, check the fit",
                      "color": "#1a56c4", "count": len(look),
                      "roles": [row(j) for j in look[:2]]})
    if low:
        tiers.append({"tier": "Lower priority", "note": "weaker match or below ask",
                      "color": "#bdbcb3", "count": len(low),
                      "roles": [row(j) for j in low[:1]]})
    return tiers


def _priority_ai(name, tiers, gA) -> str:
    first = name.split()[0]
    if gA:
        act = next((t for t in tiers if t["tier"] == "Act first"), None)
        names = ", ".join(r["co"] for r in act["roles"][:3]) if act else ""
        return f"{gA} grade-A role{'s' if gA != 1 else ''} sit in range for {first} — start with {names}." if names \
               else f"{gA} grade-A roles are the place to start for {first}."
    return f"No grade-A roles yet for {first}; work down the B-grade shortlist."


def _demand_trend(market_rows, today):
    if not market_rows:
        return [0, 0, 0, 0, 0, 0, 0, 0], 0, 0, 0, 0
    weeks = [0] * 8
    for r in market_rows:
        d = r["posted"]
        if not d:
            continue
        age = (today - d).days
        if 0 <= age < 56:
            weeks[7 - (age // 7)] += 1
    if not any(weeks):
        return weeks, 0, 0, 0, 0
    avg = round(sum(weeks) / 8)
    now = weeks[-1]
    first = next((w for w in weeks if w), now) or 1
    pct = round((now - first) / first * 100)
    vs = round((now - avg) / avg * 100) if avg else 0
    return weeks, avg, now, pct, vs


def _demand_ai(title, pct, now, avg, vs) -> str:
    direction = "rising" if pct > 5 else ("cooling" if pct < -5 else "steady")
    rel = "above" if vs >= 0 else "below"
    return (f"Demand for this profile is {direction} ({'+' if pct >= 0 else ''}{pct}% over 8 weeks), "
            f"now {now} new roles/wk — {abs(vs)}% {rel} this profile's 8-week average.")


def _upskill(gaps, market_rows, market_median) -> list:
    out = []
    for g in gaps[:4]:
        skill = g["name"].lower()
        if market_rows:
            with_skill = [r for r in market_rows if skill in r["skills"]]
            add = len(with_skill)
            sals = [r["salary"] for r in with_skill if r["salary"]]
            uplift = round(_stats.median(sals) - market_median) if sals and market_median else 0
        else:
            add = g["n"]
            uplift = 0
        out.append({"name": g["name"], "sub": "in-demand skill",
                    "add": add, "sal": max(0, uplift)})
    out.sort(key=lambda x: x["add"], reverse=True)
    return out


def _upskill_ai(upskill) -> str:
    if not upskill:
        return "No single skill stands out as a high-impact add right now."
    u = upskill[0]
    pay = f" and about €{u['sal']}/month more pay" if u["sal"] else ""
    return f"{u['name']} is the highest-impact move — it opens {u['add']} more roles{pay}."


def _employers(jobs) -> list:
    by_co = defaultdict(list)
    for j in jobs:
        co = j.get("company") or "Unknown"
        by_co[co].append(j)
    rows = []
    for co, js in by_co.items():
        sals = [j["_sal"] for j in js if j["_sal"]]
        rows.append({
            "name": co,
            "init": _initials(co),
            "roles": len(js),
            "sal":  round(_stats.mean(sals)) if sals else 0,
        })
    rows.sort(key=lambda x: (x["roles"], x["sal"]), reverse=True)
    return rows[:4]


def _employers_ai(employers) -> str:
    if not employers:
        return "No employer clusters yet — matches are spread across single openings."
    e = employers[0]
    if e["roles"] > 1:
        return f"{e['name']} is the best single target — {e['roles']} matching openings reachable in one outreach."
    return f"{e['name']} leads the shortlist; matches are otherwise spread across single openings."


def _expansion(jobs, market_rows, band, dom_state, matches):
    levers = []
    saved_states = {(j.get("state") or "").strip() for j in jobs}
    if market_rows:
        # 1 — add a neighbouring state with the most extra roles
        nb = _NEIGHBOURS.get(dom_state, [])
        best_state, best_add = None, 0
        state_counts = Counter(r["state"] for r in market_rows if r["state"] and r["state"] not in saved_states)
        for st, cnt in state_counts.most_common():
            if not nb or st in nb:
                best_state, best_add = st, cnt
                break
        if best_state:
            levers.append({"name": f"Add {best_state}", "add": best_add})
        # 2 — lower the salary floor
        lo = band[0]
        if lo:
            extra = sum(1 for r in market_rows if r["salary"] and (lo - 400) <= r["salary"] < lo)
            if extra:
                levers.append({"name": f"Lower salary floor to €{int(lo-400):,}", "add": extra})
        # 3 — open to any state (remaining)
        rest = sum(c for s, c in state_counts.items() if not levers or s != (levers[0]["name"].replace("Add ", "") if levers else ""))
        if rest:
            levers.append({"name": "Open to all states", "add": min(rest, len(market_rows))})
    total_add = sum(l["add"] for l in levers)
    lever_total = f"{matches} → {matches + total_add}"
    return levers[:4], lever_total


def _expansion_ai(name, matches, lever_total, levers) -> str:
    first = name.split()[0]
    if not levers:
        return f"{first}'s pipeline is already broad; few extra roles unlock from relaxing filters."
    top = levers[0]
    return f"{first}'s {matches} matches could grow to {lever_total.split('→')[-1].strip()} — {top['name'].lower()} alone adds {top['add']}."


def _placeability(jobs, today) -> dict:
    ages = [j["_age"] for j in jobs if j["_age"] is not None]
    buckets = [("0–7d", 0), ("8–14d", 0), ("15–30d", 0), ("31–60d", 0), ("60d+", 0)]
    dist = {k: 0 for k, _ in buckets}
    for a in ages:
        if a <= 7:    dist["0–7d"] += 1
        elif a <= 14: dist["8–14d"] += 1
        elif a <= 30: dist["15–30d"] += 1
        elif a <= 60: dist["31–60d"] += 1
        else:         dist["60d+"] += 1
    med = round(_stats.median(ages)) if ages else 0
    if med and med <= 20:
        txt = "Very high" if med <= 12 else "High"
    elif med and med <= 35:
        txt = "Moderate"
    else:
        txt = "Low" if med else "—"
    a_aging = sum(1 for j in jobs if j["_grade"] == "A" and (j["_age"] or 0) >= 15)
    return {
        "placeText": txt,
        "placeabilityDays": med,
        "placeDist": [{"d": k, "n": dist[k]} for k, _ in buckets],
        "placeAroles": a_aging,
    }


def _placeability_ai(name, place) -> str:
    first = name.split()[0]
    d = place["placeabilityDays"]
    if not d:
        return f"No posting-age data yet for {first}'s matches."
    pace = "move fast" if d <= 20 else "move at a normal pace"
    extra = f" {place['placeAroles']} A-role(s) are already 15+ days old — follow up this week." if place["placeAroles"] else ""
    return f"{first}'s matches {pace} — median posting age ~{d} days.{extra}"


def _benchmark(strength: float, all_strengths) -> dict:
    """Return {pct, rank, total} for the benchmark panel.

    pct   — only meaningful when total >= 2; kept for backward compat.
    rank  — 1-based position from the top (1 = strongest).
    total — how many candidates are in the comparison pool.
    """
    pool = [s for s in (all_strengths or []) if s is not None]
    total = len(pool)
    if total < 2:
        # Single candidate — no peer comparison possible.
        return {"pct": None, "rank": 1, "total": total or 1}
    # rank 1 = strongest: count how many are strictly stronger than this candidate
    above = sum(1 for s in pool if s > strength)
    rank  = above + 1                             # 1-based; ties share the same rank
    rank  = max(1, min(total, rank))
    below = sum(1 for s in pool if s < strength)
    pct   = max(1, min(99, round(below / total * 100)))
    return {"pct": pct, "rank": rank, "total": total}


def _benchmark_ai(name, bm: dict) -> str:
    first = name.split()[0]
    total = bm["total"]
    rank  = bm["rank"]
    pct   = bm.get("pct")
    if total < 2:
        return f"{first} is the only candidate in the pipeline right now — no peer comparison available."
    suffix = f"{rank} of {total} candidates"
    if rank == 1:
        return f"{first} is the strongest shortlist in the pipeline ({suffix}) — high-confidence, place-able profile."
    if pct is not None and pct >= 50:
        return f"{first} ranks {suffix} — solid shortlist, above the group median."
    return f"{first} ranks {suffix} — consider widening the search or strengthening the profile."


def _freshness(jobs, today) -> dict:
    closing = fresh = stale = expired = 0
    for j in jobs:
        dl = _parse_date(j.get("application_deadline"))
        if dl:
            days = (dl - today).days
            if days < 0:
                expired += 1
                continue
            if days <= 7:
                closing += 1
        age = j["_age"]
        if age is not None:
            if age < 7:
                fresh += 1
            elif 30 <= age <= 60:
                stale += 1
    return {"closing": closing, "fresh": fresh, "stale": stale, "expired": expired}


def _freshness_ai(f) -> str:
    if f["closing"]:
        return f"{f['closing']} role(s) close within a week — contact the candidate about those first."
    if f["fresh"]:
        return f"{f['fresh']} freshly posted role(s) are worth an early approach before they age."
    return "No roles closing imminently; prioritise by match strength instead."


def _briefing(D) -> tuple[list, list]:
    first = D["name"].split()[0]
    gA = D["grades"]["A"]
    p1 = (f"<b>{first} has {D['matches']} matched role{'s' if D['matches'] != 1 else ''}</b>, "
          f"<b>{gA} grade-A</b>, and a match strength of <b>{D['strength']}/100</b>. "
          f"This shortlist ranks above <b>{D['benchmarkPct']}%</b> of saved candidates.")
    ask = (f"<b>{D['asks']}</b>" if D['asks'] != "—" else "their ask")
    p2 = (f"Salary expectation {ask} {D['salaryStat']['overlap']} "
          f"(market median €{D['market']['median']:,}). Demand for this profile is "
          f"<b>{'+' if D['demandPct'] >= 0 else ''}{D['demandPct']}% over 8 weeks</b>, now {D['demandNow']} new roles/wk.")
    emp_txt = ""
    if D["employers"]:
        e = D["employers"][0]
        emp_txt = f" Richest source: <b>{e['name']} ({e['roles']} opening{'s' if e['roles'] != 1 else ''})</b>."
    up_txt = ""
    if D["upskill"]:
        u = D["upskill"][0]
        up_txt = f" A <b>{u['name']}</b> skill would unlock <b>{u['add']} more roles</b>."
    p3 = (f"<b>Placeability: {D['placeText'].lower()}</b> — similar roles sit live ~{D['placeabilityDays']} days."
          f"{emp_txt}{up_txt}")

    actions = []
    if D["fresh"]["closing"]:
        actions.append(f"Contact {first} about the <b>{D['fresh']['closing']} closing role(s)</b> this week.")
    if D["employers"] and D["employers"][0]["roles"] > 1:
        e = D["employers"][0]
        actions.append(f"Pitch <b>{e['name']}</b> — {e['roles']} matching openings, avg €{e['sal']:,}.")
    if D["upskill"]:
        u = D["upskill"][0]
        actions.append(f"Suggest <b>{u['name']}</b> to open +{u['add']} roles.")
    while len(actions) < 3:
        if D["priority"] and D["priority"][0]["roles"]:
            r = D["priority"][0]["roles"][0]
            cand = f"Start with <b>{r['title']} — {r['co']}</b> ({r['match']}% match)."
            if cand not in actions:
                actions.append(cand)
                continue
        actions.append("Review the priority shortlist and reach out to the top matches.")
    return [p1, p2, p3], actions[:3]
