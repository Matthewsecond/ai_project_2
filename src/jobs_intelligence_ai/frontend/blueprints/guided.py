"""
tabs/guided.py — Guided candidate builder.

A conversational front-end for assembling a "template candidate" spec.
The chat (proactive guide) asks the HR manager questions and fills out a set
of multi-select fields; the HR manager can also edit those fields by hand.
Both write to one shared draft object, which the client owns and ships with
every request — so the assistant always sees manual edits.

Route:
  POST /api/guided/chat   body: { message, draft, user_edits }
        → { ok, reply, next_question, field_updates, draft, facets }

Fields are FREE-TEXT — there is no fixed enum. But the funnel is DATA-GROUNDED:
after each turn we query the live job database for what actually exists given
the spec so far (how many jobs match, which occupational groups and regions
dominate) and feed those real numbers + options to the assistant, so it asks
concrete, progressively-narrowing questions instead of vague open ones.
Matching downstream is vector search over a candidate-description blob.
"""
import json as _json
import statistics
from functools import lru_cache
from flask import Blueprint, request, jsonify
from sqlalchemy import text

from jobs_intelligence_ai import config
from jobs_intelligence_ai.infra.database import get_engine
from jobs_intelligence_ai.core import taxonomy as categories   # predefined Sector → role-family taxonomy
from jobs_intelligence_ai.services.candidate import extract_guided_fields, phrase_guided_reply

bp = Blueprint("guided", __name__, url_prefix="/api/guided")

_DB = config.DB_SCHEMA


@bp.before_request
def _require_guided_support():
    """The guided funnel is built on Austria's occupational_group taxonomy.
    Countries without it (e.g. Slovakia) get a clean 404 instead of a DB error."""
    if not config.HAS_GUIDED:
        return jsonify({
            "ok": False,
            "error": f"The guided builder is not available for {config.COUNTRY_LABEL}.",
        }), 404

# Which draft fields are list-valued (merge/extend) vs scalar (replace).
# `sector` holds chosen Sector labels/ids (LLM-classified, multi-allowed); role
# families and typed job titles both live in `roles` ("Target role").
_LIST_FIELDS   = ["roles", "skills", "levels", "states", "sector", "languages", "certs"]
_SCALAR_FIELDS = ["name", "salary", "availability", "notes"]

# Which facet a quick-pick question targets → which draft field its chips fill.
_FACET_FIELD   = {"sector": "sector", "role": "roles", "states": "states"}


# ── Live facets: what the job DB actually contains for the spec so far ──────────
def _facets(draft: dict) -> dict:
    """Aggregate the live job DB for the current target, via the predefined taxonomy.

    Returns { total, groups:[{value,n}], states:[{value,n}], stage, sector }.

    The role funnel is a curated two-tier taxonomy (taxonomy.py), NOT a raw
    GROUP BY occupational_group — so chips are a small, stable, human set with real
    counts. Funnel stage is derived from what's already chosen in the draft:
      - "sectors"  : no sector picked yet → groups are the 14 sectors (facet "sector")
      - "families" : exactly one sector, has sub-families, and NONE chosen yet →
                     groups are its role families (facet "role")
      - "done"     : a role family is chosen, or 2+ sectors, or the sector has no
                     families — the role axis is settled, move to another dimension
    A target may span SEVERAL sectors; with 2+ chosen we skip family narrowing
    (it's cross-sector). `states` are suggested only while no region is chosen.
    Best-effort; never raises.
    """
    out = {"total": 0, "groups": [], "states": [], "stage": None, "sectors": []}
    states    = [s for s in (draft.get("states") or []) if s]
    sector_vals = [s for s in (draft.get("sector") or []) if s]
    role_vals = [r for r in (draft.get("roles") or []) if r]
    # Resolve sectors from the chosen Sector field first, else infer from the user's
    # role wording (so a typed "IT"/"Java developer" still grounds the funnel).
    sec_ids = categories.sector_ids(sector_vals) or categories.sector_ids(role_vals)
    out["sectors"] = sec_ids
    col = "j.occupational_group"

    try:
        with get_engine().connect() as conn:
            where  = ["j.status IN ('new','updated')",
                      "j.occupational_group IS NOT NULL",
                      "j.occupational_group <> 'keine Zuordnung'"]
            params: dict = {}
            if sec_ids:
                where.append(categories.sectors_where(col, sec_ids))
            if states:
                ph = ", ".join(f":st_{i}" for i in range(len(states)))
                where.append(f"l.location IN ({ph})")
                params.update({f"st_{i}": s for i, s in enumerate(states)})

            base = (f"FROM {_DB}.jobs j "
                    f"JOIN {_DB}.locations l ON j.location_id = l.id "
                    f"WHERE {' AND '.join(where)}")
            out["total"] = int(conn.execute(text(f"SELECT COUNT(*) {base}"), params).scalar() or 0)

            chosen   = categories.chosen_families(sec_ids[0], role_vals) if len(sec_ids) == 1 else []
            fam_case = categories.family_case_sql(col, sec_ids[0]) if len(sec_ids) == 1 else None
            # Offer role families ONLY while none is chosen yet. Once the user has
            # picked any family, the role axis is settled → "done" (move on); don't
            # keep re-asking with the leftover families (that read as a loop).
            if len(sec_ids) == 1 and fam_case and not chosen:
                out["stage"] = "families"
                out["groups"] = [{"value": r[0], "n": int(r[1])} for r in conn.execute(
                    text(f"SELECT {fam_case} fam, COUNT(*) n {base} "
                         f"GROUP BY fam ORDER BY n DESC LIMIT 9"), params)]
            elif not sec_ids:
                out["stage"] = "sectors"
                sec_case = categories.sector_case_sql(col)
                out["groups"] = [{"value": r[0], "n": int(r[1])} for r in conn.execute(
                    text(f"SELECT {sec_case} sec, COUNT(*) n {base} "
                         f"GROUP BY sec ORDER BY n DESC LIMIT 14"), params)
                    if r[0] != categories.OTHER]
            else:
                out["stage"] = "done"   # sector set + (a family chosen | multi-sector | no families)

            if not states:   # only suggest regions while none is chosen
                out["states"] = [{"value": r[0], "n": int(r[1])} for r in conn.execute(
                    text(f"SELECT l.location, COUNT(*) n {base} "
                         f"GROUP BY l.location ORDER BY n DESC LIMIT 9"), params)]
    except Exception:
        pass   # faceting is best-effort; never break the chat
    return out


def _facets_brief(facets: dict) -> str:
    """One-line-per-dimension summary of live facets for the reply prompt."""
    if not facets.get("total"):
        return "none yet (the target is still too broad to query)"
    stage = facets.get("stage")
    g = ", ".join(f"{x['value']} ({x['n']})" for x in facets.get("groups", []))
    s = ", ".join(f"{x['value']} ({x['n']})" for x in facets.get("states", []))
    # The pool is filtered by ROLE FAMILY + REGION only — never by skills, salary,
    # seniority or languages. The model must not imply otherwise (e.g. don't say
    # "276 jobs match your spec" after the user adds a skill).
    lines = [f"- postings in this role family + chosen region(s): {facets['total']} "
             f"(this pool reflects role + location ONLY — not skills, salary, seniority or languages, "
             f"so it will not shrink when those are added)"]
    if g and stage == "sectors":
        lines.append(f"- the target has NOT been pinned to a sector yet; ask which sector (facet "
                     f'"sector"). The system supplies these real SECTOR chips: {g}')
    elif g and stage == "families":
        lines.append(f"- one sector is set; ask which role family within it (facet \"role\"). "
                     f"The system supplies these real ROLE-FAMILY chips: {g}")
    elif stage == "done":
        lines.append("- the role/sector is settled (or spans several sectors) — do NOT ask about "
                     "sector/role again; move to another dimension (region, seniority, skills, salary).")
    if s: lines.append(f"- regions in that pool: {s}")
    return "\n".join(lines)


@lru_cache(maxsize=256)
def _monthly_salary_stats(pattern: str):
    """Median + quartiles of plausible MONTHLY-gross salaries for a taxonomy REGEXP.

    `pattern` is a categories.regex_for(...) alternation over occupational_group,
    so a chosen role family/sector aggregates all the AMS groups it spans. The DB
    salary field mixes monthly and annual figures, so we keep only the plausible
    monthly window (€1,000–12,000) to drop the annual outliers, then compute
    percentiles in Python. Returns None if there isn't enough clean data.
    """
    try:
        with get_engine().connect() as conn:
            rows = conn.execute(text(
                f"SELECT CAST(salary AS DECIMAL(10,2)) s FROM {_DB}.jobs "
                f"WHERE occupational_group REGEXP :re AND salary IS NOT NULL AND salary <> '' "
                f"AND CAST(salary AS DECIMAL(10,2)) BETWEEN 1000 AND 12000"),
                {"re": pattern}).fetchall()
        vals = sorted(float(r[0]) for r in rows if r[0] is not None)
    except Exception:
        return None
    if len(vals) < 8:
        return None

    def pct(p):
        i = p / 100 * (len(vals) - 1)
        lo = int(i); hi = min(lo + 1, len(vals) - 1)
        return vals[lo] + (i - lo) * (vals[hi] - vals[lo])

    return {"n": len(vals), "median": statistics.median(vals), "p25": pct(25), "p75": pct(75)}


def _salary_benchmark(draft: dict):
    """(label, stats) market benchmark for the chosen sector/role family, or None.

    Resolves the draft's chosen Sector + Target-role labels to the underlying
    taxonomy REGEXP (categories.regex_for_target) and aggregates clean monthly
    salaries over it. The label is the chosen family (preferred) or sector.
    """
    sector_vals = [x for x in (draft.get("sector") or []) if x]
    role_vals   = [x for x in (draft.get("roles") or []) if x]
    pattern     = categories.regex_for_target(sector_vals, role_vals)
    if not pattern:
        return None
    st = _monthly_salary_stats(pattern)
    if not st:
        return None
    sec_ids = categories.sector_ids(sector_vals) or categories.sector_ids(role_vals)
    fams    = categories.chosen_families(sec_ids[0], role_vals) if len(sec_ids) == 1 else []
    label   = fams[0] if fams else (categories.label_for(sec_ids[0]) if sec_ids else "this role")
    return label, st


def _clean_region_options(options, facets: dict, lang: str = "en") -> list:
    """Validate the model's translated REGION chips against the real facet values.

    Returns [{value, label, n}] where value is a genuine German region key (the
    model can't invent one), label is its translation, and n is the live count.
    Falls back to the raw region values if the model gave nothing usable, so the
    chips always reflect real data. For German, label is forced to value.
    (Sector/role chips are supplied straight from taxonomy.py, not here.)
    """
    src    = facets.get("states") or []
    counts = {x["value"]: x["n"] for x in src}
    out, seen = [], set()
    for o in (options or []):
        if not isinstance(o, dict):
            continue
        value = (o.get("value") or "").strip()
        if value in counts and value not in seen:
            seen.add(value)
            label = value if lang == "de" else (o.get("label") or value).strip()
            out.append({"value": value, "label": label, "n": counts[value]})
    if not out:   # model returned nothing valid → fall back to raw German values
        out = [{"value": x["value"], "label": x["value"], "n": x["n"]} for x in src[:5]]
    return out[:5]


def _merge_draft(draft: dict, updates: dict) -> dict:
    """Merge field_updates into draft: list fields extend (dedup), scalars replace."""
    out = {**draft}
    for f in _LIST_FIELDS:
        if f in updates and isinstance(updates[f], list):
            existing = out.get(f) or []
            additions = [x for x in updates[f] if x]
            out[f] = list(dict.fromkeys([*existing, *additions]))
    for f in _SCALAR_FIELDS:
        if f in updates and updates[f]:
            out[f] = updates[f]
    return out


@bp.route("/chat", methods=["POST"])
def api_guided_chat():
    """Body: { message, draft, user_edits } → guided reply + merged draft + facets."""
    body       = request.get_json(silent=True) or {}
    message    = (body.get("message") or "").strip()
    draft       = body.get("draft") or {}
    user_edits  = body.get("user_edits") or []
    last_offer  = body.get("last_offer") or {}
    last_question = (body.get("last_question") or "").strip()
    last_field  = (body.get("last_field") or "").strip()   # draft field the prev Q targeted
    lang        = (body.get("lang") or "en").lower()
    if not message:
        return jsonify({"ok": False, "error": "message required"}), 400

    lang_name = {"en": "English", "de": "German"}.get(
        lang, "the same language the HR manager wrote their message in")

    # Fields the user touched by hand → tell the extractor to leave them alone.
    locked = [f for f in (_LIST_FIELDS + _SCALAR_FIELDS) if draft.get(f)]

    # Options just offered to the user, so referential answers ("all", "both",
    # "the first two") can be resolved to the actual values. `kind` is either a
    # facet (sector|role|states) or, for open-dimension quick-replies, the draft
    # field directly (skills, levels, …); map it to the field its chips fill.
    offer_kind   = last_offer.get("kind")
    offer_field  = _FACET_FIELD.get(offer_kind) or (offer_kind if offer_kind in _LIST_FIELDS else None)
    offer_values = [v for v in (last_offer.get("values") or []) if v]
    offer_line   = "none"
    if offer_field and offer_values:
        offer_line = (f'You just offered the user these {offer_field} options: '
                      f'{_json.dumps(offer_values, ensure_ascii=False)}. '
                      f'If their message is a referential selection of those options '
                      f'(e.g. "all", "all of them", "choose all", "both", "the first two", "yes all"), '
                      f'expand it to the exact matching value(s) and add them to "{offer_field}". '
                      f'Copy the values verbatim.')

    # Salary benchmark from the role chosen in earlier turns, so a confirmation
    # like "yes, set it" / "use the market rate" resolves to a concrete value.
    salary_line = "none"
    bench = _salary_benchmark(draft)
    if bench and not draft.get("salary"):
        g, st = bench
        rng = f"€{int(st['p25'])}–€{int(st['p75'])}/month"
        salary_line = (
            f'A market salary benchmark for the target role ({g}) is {rng} (monthly gross). '
            f'If the user AGREES to use/set the suggested or market salary '
            f'(e.g. "yes", "set it", "use that", "sounds good", "go with the market rate") '
            f'without giving their own figure, set "salary" to "{rng}". '
            f'If they give their own number or range, use theirs instead.')

    # ── Pass 1: extract structured field updates + classify the sector ───────
    try:
        field_updates = extract_guided_fields(
            message,
            draft=_json.dumps(draft, ensure_ascii=False),
            locked=_json.dumps(locked, ensure_ascii=False),
            catalog=categories.sector_catalog(),
            last_field=last_field,
            offer=offer_line,
            salary=salary_line)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    # Deterministic chip-pick routing. When the user answers a facet question by
    # clicking the quick-pick chips, the front-end sends the offered values straight
    # back, comma-joined. The extractor can mis-file them, so when the message is a
    # selection of the values we just offered, file them into the offered field
    # ourselves and scrub any stray copies the extractor dropped elsewhere.
    if offer_field and offer_values:
        by_lower = {v.lower(): v for v in offer_values}
        picked   = list(dict.fromkeys(
            by_lower[p.strip().lower()]
            for p in message.split(",") if p.strip().lower() in by_lower))
        if picked:
            merged = [x for x in (field_updates.get(offer_field) or []) if x]
            field_updates[offer_field] = list(dict.fromkeys([*merged, *picked]))
            picked_lower = {v.lower() for v in picked}
            for f in _LIST_FIELDS:
                if f != offer_field and isinstance(field_updates.get(f), list):
                    field_updates[f] = [x for x in field_updates[f]
                                        if x.lower() not in picked_lower]

    # Normalize classified sectors (LLM emits ids, chips emit labels) to canonical
    # sector labels for display + consistent matching; drop anything unrecognized.
    if isinstance(field_updates.get("sector"), list):
        field_updates["sector"] = categories.normalize_sectors(field_updates["sector"])

    new_draft = _merge_draft(draft, field_updates)

    # ── Live facets: query the DB for what actually exists for this target ───
    facets = _facets(new_draft)
    # Salary benchmark only matters until a salary is set (and is cached anyway).
    salary_hint = "none available"
    if not new_draft.get("salary"):
        b2 = _salary_benchmark(new_draft)
        if b2:
            g2, s2 = b2
            salary_hint = (f"{g2} — monthly gross (Austria, n={s2['n']}): "
                           f"median €{int(s2['median'])}, typical €{int(s2['p25'])}–€{int(s2['p75'])}.")

    # ── Pass 2: phrase reply + grounded, narrowing next question ─────────────
    reply_result  = phrase_guided_reply(
        message,
        lang=lang_name,
        last_question=last_question,
        field_updates=_json.dumps(field_updates, ensure_ascii=False),
        user_edits=_json.dumps(user_edits, ensure_ascii=False) if user_edits else "none",
        draft=_json.dumps(new_draft, ensure_ascii=False),
        facets=_facets_brief(facets),
        salary_hint=salary_hint)
    reply         = reply_result.get("reply") or "Got it."
    next_question = reply_result.get("next_question") or ""
    facet_dim     = reply_result.get("facet") or ""
    # Sector & role-family chips are authoritative from the predefined taxonomy
    # (categories), so the model can't invent or mis-translate them; it only
    # decides the question. Region chips still come via the model + facet check.
    if facet_dim in ("sector", "role"):
        options = [{"value": x["value"], "label": x["value"], "n": x["n"]}
                   for x in (facets.get("groups") or [])[:5]]
    elif facet_dim == "states":
        options = _clean_region_options(reply_result.get("options"), facets, lang)
    else:
        options = []
    # Short tappable quick-replies for non-data questions (skills, seniority, …).
    suggestions   = []
    if next_question and not options:
        suggestions = [s.strip() for s in (reply_result.get("suggestions") or [])
                       if isinstance(s, str) and s.strip()][:4]

    # Which draft field the next_question targets — sent back next turn as
    # `last_field` so the answer is filed there, and used to route quick-replies.
    # Facet questions are authoritative (map facet→field); else trust the model.
    answer_field = _FACET_FIELD.get(facet_dim) or (reply_result.get("answer_field") or "")
    if answer_field not in (_LIST_FIELDS + _SCALAR_FIELDS):
        answer_field = ""

    return jsonify({
        "ok":            True,
        "reply":         reply,
        "next_question": next_question,
        "facet":         facet_dim,
        "answer_field":  answer_field,
        "options":       options,
        "suggestions":   suggestions,
        "field_updates": field_updates,
        "draft":         new_draft,
        "facets":        facets,
    })


@bp.route("/save", methods=["POST"])
def api_guided_save():
    """Body: { draft, label? } → persist a target-candidate spec. NOT personal data."""
    from flask import session
    from jobs_intelligence_ai.services.candidate import store
    body  = request.get_json(silent=True) or {}
    draft = body.get("draft") or {}
    if not draft:
        return jsonify({"ok": False, "error": "draft required"}), 400
    created_by = session.get("display_name") or session.get("username") or None
    tid = store.save_target(draft, label=body.get("label"), created_by=created_by)
    return jsonify({"ok": True, "id": tid})


@bp.route("/targets", methods=["GET"])
def api_guided_targets():
    """List saved target-candidate specs."""
    from jobs_intelligence_ai.services.candidate import store
    return jsonify({"ok": True, "targets": store.list_targets()})
