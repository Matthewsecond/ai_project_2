"""
core/categories.py — Predefined role taxonomy for the guided funnel.

The raw AMS `occupational_group` column has ~7,600 distinct values — far too
granular to drive a "pick a role family" funnel (it's effectively free text).
This module defines a curated TWO-TIER taxonomy on top of it:

    Sector  (14 buckets, ~90% of active jobs)  →  Role family

Each entry maps to the underlying data by a MySQL REGEXP over `occupational_group`,
so the funnel can show a small, stable, human-readable set of chips AND still
report REAL job counts. Final candidate→job matching stays vector-based and is
unaffected by this file.

Assignment is FIRST-MATCH-WINS in list order, so patterns are ordered specific →
general (e.g. trade `*technikerIn` resolve under Construction before the generic
`Techniker` catch in Technical & Engineering). For the SAME reason a job's sector
is "matches my pattern AND none of the earlier sectors' patterns" — the helpers
below build exactly that exclusive predicate, so e.g. Technical & Engineering does
NOT re-absorb the trade technicians already claimed by Construction.

Counts in the comments are from the live DB (status IN ('new','updated'),
excluding 'keine Zuordnung') and are indicative, not asserted at runtime.

Public surface:
    SECTORS, FAMILIES                          # the taxonomy data
    OTHER                                       # label for the residual bucket
    find_sector(values)  -> sector_id | None    # reverse-lookup a chosen label
    family_labels(id) / chosen_families(id, vs)
    sector_case_sql(col) / family_case_sql(col, id) / sector_where(col, id)
    regex_for(values)    -> combined REGEXP for the chosen sector/families
"""
import re

OTHER = "Other"

# ── Tier 1: sectors (ordered — first match wins) ───────────────────────────────
SECTORS = [
    {"id": "healthcare",   "label": "Healthcare & Care",
     "desc": "Nursing, elderly/disability care, doctors, dentists, therapists, pharmacy, paramedics, opticians.",
     "pattern": r"Pfleg|Gesundheit|Arzt|Ärzt|Krankenpfleg|Heimhelf|Sozialbetreu|ZahnärztlicheR|Hebamme|Sanitäter|Therapeut|Ordinationsass|Apotheke|Pharmazeut|Augenoptik|Hörgeräteakustik"},          # ~7,840
    {"id": "beauty",       "label": "Beauty & Personal Care",
     "desc": "Hairdressing, cosmetics, nails, barbering, massage and personal grooming.",
     "pattern": r"Friseur|Kosmetik|Stylist|Masseur|Nageldesign|FußpflegerIn"},               # ~1,160
    {"id": "education",    "label": "Education & Childcare",
     "desc": "Teachers, tutors, kindergarten/childcare staff, social pedagogy.",
     "pattern": r"Pädagog|Kinderbetreu|Erzieher|Lehrer|Nachhilfe|Hort|Betreuung"},           # ~1,020
    {"id": "hospitality",  "label": "Hospitality & Gastronomy",
     "desc": "Restaurants, hotels, catering: chefs, cooks, kitchen help, waiting staff, reception, bar.",
     "pattern": r"Koch|Köch|Restaurant|Kellner|Servier|Küche|Stuben|Barkeep|Barista|Rezeptionist|Gaststätten|Abwäscher|Servicekraft|Hotel|Buffet|Schank|Gastronomie"},   # ~11,670
    {"id": "it",           "label": "IT & Software",
     "desc": "Software development, IT, SAP/ERP, networks & sysadmin, data, IT security, IT support.",
     "pattern": r"Software|Informatik|SAP|Netzwerk|Systemadmin|DevOps|Datenbank|Webentwic|Applikationsentwic|Programmier|IT-Tech|IT-Projektmanag|IT-Support|Datensicherheit"},   # ~2,440
    {"id": "construction", "label": "Construction & Trades",
     "desc": "Skilled manual trades: electricians, plumbers/HVAC, metalwork/welding, mechanics, carpenters, masons, painters, roofers.",
     "pattern": r"Maurer|Zimmer|Tischler|Elektr|Installat|Schlosser|Schweiß|Schweiss|Maschinenbau|Mechatronik|Mechanik|Lackier|Karosserie|Metall|Zerspanung|Dachdeck|Maler|Spengler|Bautechnik|Bauhelf|Baumaschin|Hochbau|Tiefbau|Fliesen|Beton|Bodenleg|Fassad|Stuckateur|Trockenausbau|Rauchfangkehr|Kälteanlage|Kunststofftechnik|Anlagentechnik|Betriebstechnik|Instandhaltung|Baunebengewerbe"},   # ~23,420
    {"id": "logistics",    "label": "Logistics & Transport",
     "desc": "Warehouse, drivers/freight (truck, delivery), couriers, logistics coordination.",
     "pattern": r"Lager|Logistik|Fahrer|Kraftfahr|Lkw|Berufskraftfahr|Zusteller|Stapler|Kurier|Bote|Post|Taxi|Chauffeur"},   # ~5,910
    {"id": "retail",       "label": "Retail & Sales",
     "desc": "Shop floor sales, cashiers, field sales reps, wholesale/procurement.",
     "pattern": r"Einzelhandel|Verkäuf|Kassier|Handelsvertret|Salesmanag|Verkauf|Feinkost|Großhandel|Einrichtungsberater|Tankwart|Vertrieb"},   # ~12,990
    {"id": "office",       "label": "Office / Finance & Legal",
     "desc": "Office admin/clerical, accounting & payroll, banking/insurance, legal, finance advisory, call centre.",
     "pattern": r"Bürokaufmann|Bürokraft|Buchhalt|Personalverrechn|Sekretär|Sachbearbeit|Controll|Assistenz|Bank|Versicherung|Jurist|Wirtschaftstreuhänd|Unternehmensberater|BetriebswirtIn|Einkäufer|Steuerberat|Callcenter"},   # ~4,920
    {"id": "production",   "label": "Production & Manufacturing",
     "desc": "Factory production & machine operation, food production (bakery/butchery), plastics & wood processing.",
     "pattern": r"Produktion|Fertigung|Maschinenführer|Maschinenbedien|MetallbearbeiterIn|Bäcker|Konditor|Fleisch|Lebensmitteltechnik|Holzverarbeitung"},   # ~4,000
    {"id": "cleaning",     "label": "Cleaning & Facility",
     "desc": "Cleaning, housekeeping, caretaker/janitor and facility services.",
     "pattern": r"Reinigung|Raumpfleg|Hausbetreu|Gebäudereinig|Hausbesorg|Hausmeister"},      # ~730
    {"id": "security",     "label": "Security",
     "desc": "Security guards, surveillance and protective services.",
     "pattern": r"Sicherheits|Bewach|Portier"},                                              # ~240
    {"id": "engineering",  "label": "Technical & Engineering",
     "desc": "Engineers, technicians (service/maintenance), automation, quality assurance, technical drawing/design. NOT hands-on trades (those are Construction & Trades).",
     "pattern": r"Techniker|Ingenieur|Konstrukt|TechnischeR ZeichnerIn|Qualitätssicher|Automatisierung"},   # ~3,150
    {"id": "management",   "label": "Management & Business",
     "desc": "General management, executives, team/department leads, project managers (not tied to a specific trade above).",
     "pattern": r"Manager|Geschäftsführ|Teamleiter|Projektmanag"},                            # ~1,780
]

# ── Tier 2: role families within a sector (ordered — first match wins) ──────────
# Order MUST match the order each set was count-validated against the DB, because
# first-match-wins assignment depends on it. Sectors without families fall back to
# the raw sector facet (see helpers). Family counts are the live in-sector totals.
FAMILIES = {
    "it": [
        {"label": "Software Development",    "pattern": r"Softwareentwic|Programmier|Applikationsentwic|Webentwic|DevOps"},   # ~970
        {"label": "Network & Systems Admin", "pattern": r"Netzwerk|Systemadmin|IT-Tech|Systemtechnik"},                       # ~345
        {"label": "SAP / ERP",               "pattern": r"SAP"},                                                              # ~270
        {"label": "Informatics (general)",   "pattern": r"Informatik"},                                                       # ~255
        {"label": "IT Project & Consulting", "pattern": r"IT-Projektmanag|IT-BeraterIn|IT-ConsultantIn"},                     # ~200
        {"label": "IT Support",              "pattern": r"IT-Support|Helpdesk|AnwendertechnikerIn|IT-BetreuerIn"},            # ~185
        {"label": "IT Security",             "pattern": r"Datensicherheit|Security|Cyber"},                                   # ~110
        {"label": "Data & Databases",        "pattern": r"Datenbank|Data|Business Intelligence"},                             # ~45
    ],
    "construction": [
        {"label": "Electrical",                "pattern": r"Elektr"},                                                                 # ~4,830
        {"label": "HVAC & Plumbing",           "pattern": r"Installat|Gebäudetechnik|Kälteanlage|Heizung|Sanitär|Lüftung"},          # ~1,730
        {"label": "Metalwork & Welding",       "pattern": r"Schlosser|Schweiß|Schweiss|Zerspanung|Metall|Schmied"},                  # ~4,290
        {"label": "Mechanics (Vehicle/Machine)","pattern": r"Mechatronik|Mechanik|Karosserie|Maschinenbau"},                         # ~3,730
        {"label": "Painting & Coating",        "pattern": r"Maler|Lackier|Anstreich"},                                              # ~1,020
        {"label": "Carpentry & Wood",          "pattern": r"Tischler|Zimmer|Bodenleg|Holz"},                                        # ~2,510
        {"label": "Masonry & Structural",      "pattern": r"Maurer|Beton|Hochbau|Tiefbau|Fliesen|Fassad|Stuckateur|Trockenausbau"}, # ~2,500
        {"label": "Roofing & Chimney",         "pattern": r"Dachdeck|Spengler|Rauchfangkehr"},                                      # ~1,000
    ],
    "hospitality": [
        {"label": "Kitchen & Chef",            "pattern": r"Koch|Köch|Gaststättenkoch|KüchenchefIn"},               # ~3,630
        {"label": "Kitchen Help & Dishwashing","pattern": r"Küchenhilf|Abwäscher"},                                 # ~1,470
        {"label": "Service & Waiting",         "pattern": r"Kellner|Servier|Servicekraft|Buffet|Schank|Stuben"},    # ~2,740
        {"label": "Front Desk & Reception",    "pattern": r"Rezeptionist|Hotel"},                                   # ~1,230
        {"label": "Bar",                       "pattern": r"Barkeep|Barista"},                                       # ~130
    ],
    "retail": [
        {"label": "Cashier",                 "pattern": r"Kassier"},                                       # ~950
        {"label": "Field Sales & Reps",      "pattern": r"Handelsvertret|Salesmanag|Vertrieb|Außendienst"},# ~1,300
        {"label": "Wholesale & Procurement", "pattern": r"Großhandel|Einkäufer"},                          # ~200
        {"label": "Petrol Station",          "pattern": r"Tankwart"},                                      # ~135
        {"label": "Specialist Advisors",     "pattern": r"Einrichtungsberater"},                           # ~120
        {"label": "Retail Sales Staff",      "pattern": r"Einzelhandel|Verkäuf|Feinkost|Verkauf"},         # ~10,850
    ],
    "healthcare": [
        {"label": "Nursing",               "pattern": r"Krankenpfleg|PflegeassistentIn|PflegefachassistentIn|DiplomierteR Gesundheits"},   # ~2,680
        {"label": "Care & Social Support", "pattern": r"Heimhelf|Sozialbetreu|Pflegehelf|Altenbetreu"},     # ~980
        {"label": "Doctors",               "pattern": r"Arzt|Ärzt|Facharzt"},                               # ~1,770
        {"label": "Dental",                "pattern": r"Zahn|ZahnärztlicheR"},                              # ~400
        {"label": "Therapy",               "pattern": r"Therapeut|Physio|Ergotherapie|Logopäd"},           # ~360
        {"label": "Pharmacy",              "pattern": r"Apotheke|Pharmazeut"},                              # ~70
        {"label": "Optical & Hearing",     "pattern": r"Augenoptik|Hörgeräteakustik"},                      # ~220
        {"label": "Emergency Medical",     "pattern": r"Sanitäter"},                                        # ~15
    ],
    "logistics": [
        {"label": "Warehouse",              "pattern": r"Lager|Stapler"},                                          # ~2,250
        {"label": "Driving & Freight",      "pattern": r"Lkw|Kraftfahr|Berufskraftfahr|Chauffeur|Taxi|FahrerIn"},  # ~2,320
        {"label": "Delivery & Courier",     "pattern": r"Zusteller|Kurier|Bote|Post"},                             # ~400
        {"label": "Logistics Coordination", "pattern": r"Logistik"},                                               # ~1,140
    ],
    "office": [
        {"label": "Accounting & Payroll",       "pattern": r"Buchhalt|Personalverrechn|Controll"},                          # ~1,710
        {"label": "Banking & Insurance",        "pattern": r"Bank|Versicherung"},                                           # ~645
        {"label": "Legal",                      "pattern": r"Jurist|Rechtsanwalt|Notar"},                                   # ~120
        {"label": "Finance & Business Advisory","pattern": r"Wirtschaftstreuhänd|Steuerberat|Unternehmensberater|BetriebswirtIn"},  # ~610
        {"label": "Purchasing",                 "pattern": r"Einkäufer"},                                                   # ~325
        {"label": "Call Center",                "pattern": r"Callcenter"},                                                  # ~140
        {"label": "Office Administration",      "pattern": r"Bürokaufmann|Bürokraft|Sekretär|Sachbearbeit|Assistenz"},     # ~2,030
    ],
    "production": [
        {"label": "Food Production",            "pattern": r"Bäcker|Konditor|Fleisch|Lebensmitteltechnik"},        # ~1,200
        {"label": "Plastics Processing",        "pattern": r"Kunststoff"},                                         # ~95
        {"label": "Wood Processing",            "pattern": r"Holzverarbeitung|Holz"},                              # ~270
        {"label": "Production & Machine Operation","pattern": r"Produktion|Fertigung|Maschinenführer|Maschinenbedien"},  # ~3,420
    ],
    "engineering": [
        {"label": "Engineers",                 "pattern": r"Ingenieur"},               # ~250
        {"label": "Automation",                "pattern": r"Automatisierung"},         # ~230
        {"label": "Quality Assurance",         "pattern": r"Qualitätssicher"},         # ~275
        {"label": "Technical Drawing & Design","pattern": r"Konstrukt|ZeichnerIn"},    # ~225
        {"label": "Service Technicians",       "pattern": r"Servicetechnik"},          # ~400
        # everything else technical falls into the residual "Other" chip (~1,770)
    ],
    # Small sectors below — families are sensible groupings but NOT count-validated.
    "beauty": [
        {"label": "Hairdressing & Styling", "pattern": r"Friseur|Stylist"},
        {"label": "Cosmetics & Nails",      "pattern": r"Kosmetik|Nageldesign"},
        {"label": "Massage & Foot Care",    "pattern": r"Masseur|FußpflegerIn"},
    ],
    "education": [
        {"label": "Childcare & Kindergarten", "pattern": r"Kinderbetreu|Elementarpädagog|Kindergarten|Hort"},
        {"label": "Teaching & Tutoring",      "pattern": r"Lehrer|Nachhilfe"},
        {"label": "Social Pedagogy",          "pattern": r"Sozialpädagog"},
    ],
    "management": [
        {"label": "Project Management",       "pattern": r"Projektmanag"},
        {"label": "Team & Department Leads",  "pattern": r"Teamleiter"},
        {"label": "Executives",               "pattern": r"Geschäftsführ"},
        {"label": "General Management",       "pattern": r"Manager"},
    ],
    # cleaning, security: no sub-families (small) — funnel stops at the sector.
}

# ── Intent keywords: map what a USER types to a sector ─────────────────────────
# The sector patterns above match the German AMS taxonomy, not free text — so a
# typed "IT" or "nursing" wouldn't resolve. These whole-word keywords bridge the
# user's wording (EN + common DE) to a sector so the funnel can jump straight to
# that sector's role families instead of offering the biggest sectors by count.
# Matched as whole tokens (not substrings) to avoid e.g. "care" hitting "childcare".
SECTOR_KEYWORDS = {
    "healthcare":   {"health", "healthcare", "care", "nursing", "nurse", "medical", "doctor", "physician", "caregiver", "pflege", "gesundheit", "kranken", "arzt", "pfleger"},
    "beauty":       {"beauty", "hairdresser", "hairdressing", "hairstylist", "barber", "cosmetics", "cosmetic", "manicure", "nails", "friseur", "kosmetik"},
    "education":    {"education", "teacher", "teaching", "childcare", "kindergarten", "tutor", "tutoring", "pedagogue", "lehrer", "erzieher"},
    "hospitality":  {"hospitality", "gastronomy", "restaurant", "hotel", "catering", "chef", "cook", "kitchen", "waiter", "waitress", "bartender", "barista", "gastro", "koch", "kellner", "gastronomie"},
    "it":           {"it", "ict", "software", "developer", "dev", "programmer", "programming", "informatics", "sysadmin", "devops", "informatik", "edv", "coder"},
    "construction": {"construction", "trades", "trade", "tradesman", "craftsman", "builder", "electrician", "plumber", "carpenter", "welder", "mason", "handwerk", "bau", "elektriker", "maurer"},
    "logistics":    {"logistics", "transport", "transportation", "warehouse", "driver", "driving", "courier", "shipping", "forklift", "lager", "logistik", "fahrer", "spedition"},
    "retail":       {"retail", "sales", "salesperson", "salesman", "shop", "store", "cashier", "merchandiser", "verkauf", "handel", "einzelhandel", "kassier", "verkäufer"},
    "office":       {"office", "finance", "financial", "legal", "accounting", "accountant", "admin", "administration", "administrative", "clerk", "secretary", "banking", "bank", "insurance", "büro", "buchhaltung", "sekretär"},
    "production":   {"production", "manufacturing", "factory", "assembly", "fabrication", "producer", "produktion", "fertigung"},
    "cleaning":     {"cleaning", "cleaner", "janitor", "facility", "housekeeping", "reinigung", "raumpflege"},
    "security":     {"security", "guard", "watchman", "surveillance", "sicherheit", "bewachung"},
    "engineering":  {"engineering", "engineer", "technician", "technical", "mechanical", "ingenieur", "techniker", "konstruktion"},
    "management":   {"management", "manager", "executive", "leadership", "business", "director", "geschäftsführung", "führungskraft"},
}


def resolve_sector_from_text(value):
    """Sector id implied by a user's free-text words (whole-token match), else None.

    First sector in SECTORS order whose keyword set intersects the value's tokens.
    """
    toks = set(re.findall(r"[a-zà-ÿ]+", (value or "").lower()))
    if not toks:
        return None
    for s in SECTORS:
        if toks & SECTOR_KEYWORDS.get(s["id"], set()):
            return s["id"]
    return None


# ── Reverse lookups (chosen chip label → taxonomy) ─────────────────────────────
_SECTOR_BY_LABEL = {s["label"]: s["id"] for s in SECTORS}
_SECTOR_IDS      = {s["id"] for s in SECTORS}


def _sector_by_id(sector_id):
    return next((s for s in SECTORS if s["id"] == sector_id), None)


def find_sector(values):
    """Sector id implied by the chosen values, else None.

    Prefers an exact sector label/id (what the funnel chips store), then falls
    back to mapping a raw AMS occupational_group value — so a manual edit via the
    draft's category dropdown, or a legacy draft, still resolves to its sector.
    """
    for v in values or []:
        if v in _SECTOR_BY_LABEL:
            return _SECTOR_BY_LABEL[v]
        if v in _SECTOR_IDS:
            return v
    for v in values or []:                 # typed intent: "IT", "nursing", "sales"…
        sid = resolve_sector_from_text(v)
        if sid:
            return sid
    for v in values or []:                 # raw AMS taxonomy value (manual / legacy)
        sid = sector_for(v)
        if sid:
            return sid
    return None


def families_for(sector_id):
    return FAMILIES.get(sector_id, [])


def family_labels(sector_id):
    return [f["label"] for f in families_for(sector_id)]


def chosen_families(sector_id, values):
    """Which of the chosen values are role families of this sector."""
    fl = set(family_labels(sector_id))
    return [v for v in (values or []) if v in fl]


def sector_for(occ_group):
    """Sector id a raw AMS occupational_group falls into (first match), or None."""
    if not occ_group:
        return None
    for s in SECTORS:
        if re.search(s["pattern"], occ_group):
            return s["id"]
    return None


# ── SQL builders (patterns are trusted constants — safe to inline) ─────────────
def _earlier_union(sector_id):
    """OR of every sector pattern ranked before this one (for exclusive membership)."""
    pats = []
    for s in SECTORS:
        if s["id"] == sector_id:
            break
        pats.append(s["pattern"])
    return "|".join(pats)


def sector_where(col, sector_id):
    """SQL predicate: rows whose first-match sector is exactly `sector_id`."""
    sec = _sector_by_id(sector_id)
    if not sec:
        return "1=1"
    clause = f"{col} REGEXP '{sec['pattern']}'"
    earlier = _earlier_union(sector_id)
    if earlier:
        clause += f" AND {col} NOT REGEXP '{earlier}'"
    return clause


def sector_case_sql(col):
    """SQL CASE mapping a row to its sector label (first match wins), else OTHER."""
    whens = " ".join(f"WHEN {col} REGEXP '{s['pattern']}' THEN '{s['label']}'" for s in SECTORS)
    return f"CASE {whens} ELSE '{OTHER}' END"


def family_case_sql(col, sector_id):
    """SQL CASE mapping an in-sector row to its family label, else 'Other …'.

    Caller is responsible for restricting rows to the sector (sector_where).
    """
    fams = families_for(sector_id)
    if not fams:
        return None
    whens = " ".join(f"WHEN {col} REGEXP '{f['pattern']}' THEN '{f['label']}'" for f in fams)
    sec = _sector_by_id(sector_id)
    other = f"Other {sec['label']}" if sec else OTHER
    return f"CASE {whens} ELSE '{other}' END"


def regex_for(values):
    """Combined REGEXP for the chosen sector/families (for counts or salary stats).

    If specific families are chosen, returns their union (narrow); otherwise the
    whole sector pattern. Returns None if nothing recognizable was chosen.
    """
    sector_id = find_sector(values)
    if not sector_id:
        return None
    fams = [f for f in families_for(sector_id) if f["label"] in set(values or [])]
    if fams:
        return "|".join(f["pattern"] for f in fams)
    sec = _sector_by_id(sector_id)
    return sec["pattern"] if sec else None


# ── Multi-sector helpers (a candidate target may span several sectors) ─────────
def sector_ids(values):
    """All distinct sector ids the chosen values resolve to, in chip order."""
    out = []
    for v in values or []:
        sid = (_SECTOR_BY_LABEL.get(v) or (v if v in _SECTOR_IDS else None)
               or resolve_sector_from_text(v) or sector_for(v))
        if sid and sid not in out:
            out.append(sid)
    return out


def sectors_where(col, ids):
    """SQL predicate matching rows in ANY of the given sectors (exclusive union)."""
    parts = [f"({sector_where(col, sid)})" for sid in ids if _sector_by_id(sid)]
    return "(" + " OR ".join(parts) + ")" if parts else "1=1"


def regex_for_target(sector_values, role_values):
    """REGEXP spanning the chosen sectors, narrowed to chosen families where given.

    For each chosen sector: if any of its role families are present in role_values,
    use those families' patterns (narrow); otherwise the whole sector pattern.
    Returns None when no sector is recognizable. Used for salary benchmarking.
    """
    ids = sector_ids(sector_values) or sector_ids(role_values)
    if not ids:
        return None
    chosen = set(role_values or [])
    pats = []
    for sid in ids:
        fams = [f["pattern"] for f in families_for(sid) if f["label"] in chosen]
        pats.extend(fams if fams else [_sector_by_id(sid)["pattern"]])
    return "|".join(pats) if pats else None


def label_for(sector_id):
    """Display label for a sector id (or the id itself if unknown)."""
    sec = _sector_by_id(sector_id)
    return sec["label"] if sec else sector_id


def normalize_sectors(values):
    """Canonical sector LABELS for chosen values (ids or labels), deduped.

    LLM classification emits short ids; chips emit labels — normalize both to the
    display label so the draft's Sector field is consistent. Drops unrecognized.
    """
    return [label_for(sid) for sid in sector_ids(values)]


def sector_catalog():
    """Human/LLM-readable catalog of sectors (id · label · description) for prompts."""
    return "\n".join(f'- {s["id"]} ({s["label"]}): {s["desc"]}' for s in SECTORS)
