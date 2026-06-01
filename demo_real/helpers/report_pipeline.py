"""
helpers/report_pipeline.py — Candidate Pipeline Report PDF ("Direction B" hi-fi look).

A warm, editorial report: cream paper, monospace uppercase labels, clean sans
headlines, terracotta accent, hairline-bordered cards, a pentagon strength radar,
an Austria opportunity map, salary histograms and per-match detail pages.

Public entry point (drop-in replacement for the old generator):
    generate_saved_jobs_pdf(jobs, candidate_profile=None) -> bytes

Requires: reportlab.  Registers Consolas/Arial from the Windows font dir when
present, falling back to ReportLab's built-in Courier/Helvetica otherwise.
"""
import io
import os
import math
from datetime import date, datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Flowable, Paragraph, Spacer, Table,
    TableStyle, PageBreak, KeepTogether, HRFlowable,
)
from reportlab.graphics.shapes import Drawing, Rect, Line, Polygon, Circle, String, Group
from reportlab.graphics import renderPDF

# Real (simplified) Austria Bundesland geometry for the opportunity map.
try:
    from .at_geo import AT_POLYGONS, AT_WIDTH, AT_HEIGHT
except Exception:  # pragma: no cover - import fallbacks for varied run contexts
    try:
        from helpers.at_geo import AT_POLYGONS, AT_WIDTH, AT_HEIGHT
    except Exception:
        from at_geo import AT_POLYGONS, AT_WIDTH, AT_HEIGHT

# ── Geometry ──────────────────────────────────────────────────────────────────
PAGE_W, PAGE_H = A4
MARGIN_X  = 1.7 * cm
MARGIN_TOP = 2.5 * cm          # header sits above the content frame
MARGIN_BOT = 1.9 * cm          # footer sits below
COL_W = PAGE_W - 2 * MARGIN_X

# ── Palette ───────────────────────────────────────────────────────────────────
PAPER   = colors.HexColor("#F7F6F1")   # warm cream page
INK      = colors.HexColor("#1A1A18")  # near-black text
MUTE     = colors.HexColor("#9A9890")  # mono labels / muted
MUTE2    = colors.HexColor("#76746C")  # slightly darker muted
FAINT    = colors.HexColor("#CBC8BC")  # dotted dividers
RULE     = colors.HexColor("#DCD9CF")  # hairlines / card borders
CHIP_BG  = colors.HexColor("#EFEDE3")  # skill chip fill
CARD_BG  = colors.HexColor("#FBFAF6")  # very subtle card fill
TRACK    = colors.HexColor("#E5E2D6")  # bar track
ACCENT   = colors.HexColor("#C2410C")  # terracotta
ACCENT_D = colors.HexColor("#9A3412")  # darker terracotta
ACCENT_HL= colors.HexColor("#FBEAE0")  # light terracotta wash (outreach / new tag)
GREEN    = colors.HexColor("#3F7A4B")
RED      = colors.HexColor("#B23B2E")
WHITE    = colors.white

HEAT = [colors.HexColor("#C2410C"), colors.HexColor("#E69B73"), colors.HexColor("#F3D8C8")]

GRADE_COLOR = {"A": ACCENT, "B": INK, "C": MUTE}

# ── Fonts ───────────────────────────────────────────────────────────────────--
FONTS = {"sans": "Helvetica", "sans_b": "Helvetica-Bold", "sans_i": "Helvetica-Oblique",
         "mono": "Courier", "mono_b": "Courier-Bold", "mono_i": "Courier-Oblique"}
_FONTS_READY = False


def _register_fonts():
    global _FONTS_READY
    if _FONTS_READY:
        return
    win = os.environ.get("WINDIR", r"C:\Windows") + r"\Fonts"

    def reg(alias, candidates, builtin):
        for fn in candidates:
            p = os.path.join(win, fn)
            if os.path.exists(p):
                try:
                    pdfmetrics.registerFont(TTFont(alias, p))
                    return alias
                except Exception:
                    continue
        return builtin

    FONTS["sans"]   = reg("DBSans",    ["arial.ttf"],            "Helvetica")
    FONTS["sans_b"] = reg("DBSans-B",  ["arialbd.ttf"],          "Helvetica-Bold")
    FONTS["sans_i"] = reg("DBSans-I",  ["ariali.ttf"],           "Helvetica-Oblique")
    FONTS["mono"]   = reg("DBMono",    ["consola.ttf", "CascadiaMono.ttf"], "Courier")
    FONTS["mono_b"] = reg("DBMono-B",  ["consolab.ttf"],         "Courier-Bold")
    FONTS["mono_i"] = reg("DBMono-I",  ["consolai.ttf"],         "Courier-Oblique")
    _FONTS_READY = True


# ── Low-level canvas helper: letter-spaced text ────────────────────────────────
def _ls(c, x, y, text, font, size, color, tracking=1.4, anchor="l"):
    """Draw letter-spaced text; returns the drawn width."""
    w = c.stringWidth(text, font, size) + tracking * max(0, len(text) - 1)
    if anchor == "r":
        x -= w
    elif anchor == "c":
        x -= w / 2.0
    t = c.beginText(x, y)
    t.setFont(font, size)
    t.setFillColor(color)
    t.setCharSpace(tracking)
    t.textOut(text)
    c.drawText(t)
    return w


# ── A mono uppercase label as a flowable (eyebrows / section labels) ───────────
class MonoLabel(Flowable):
    def __init__(self, text, size=7.5, color=MUTE, tracking=1.7, font=None,
                 anchor="l", width=None, space_after=0, space_before=0):
        Flowable.__init__(self)
        self.text = text
        self.size = size
        self.color = color
        self.tracking = tracking
        self.font = font or FONTS["mono"]
        self.anchor = anchor
        self._w = width
        self.space_after = space_after
        self.space_before = space_before

    def wrap(self, aw, ah):
        self.width = self._w if self._w is not None else aw
        self.height = self.size + self.space_after + self.space_before + 2
        return self.width, self.height

    def draw(self):
        x = {"l": 0, "c": self.width / 2.0, "r": self.width}[self.anchor]
        _ls(self.canv, x, self.space_after + 2, self.text,
            self.font, self.size, self.color, self.tracking, self.anchor)


# ── Paragraph style factory ────────────────────────────────────────────────────
def _styles():
    def s(name, **kw):
        base = {"fontName": FONTS["sans"], "textColor": INK, "leading": 14}
        base.update(kw)
        return ParagraphStyle(name, **base)
    return {
        "name":    s("name",   fontName=FONTS["sans_b"], fontSize=27, leading=30),
        "h1":      s("h1",     fontName=FONTS["sans_b"], fontSize=21, leading=24),
        "sub":     s("sub",    fontName=FONTS["sans"],   fontSize=11.5, textColor=MUTE2, leading=16),
        "body":    s("body",   fontSize=10, leading=15.5),
        "body_s":  s("body_s", fontSize=9,  leading=14, textColor=colors.HexColor("#3a3a36")),
        "kv_val":  s("kv_val", fontSize=10, leading=14),
        "italic":  s("italic", fontName=FONTS["sans_i"], fontSize=9.5, leading=14.5,
                     textColor=colors.HexColor("#54524b")),
        "job_ttl": s("job_ttl", fontName=FONTS["sans_b"], fontSize=15, leading=18),
        "match_ttl": s("match_ttl", fontName=FONTS["sans_b"], fontSize=11.5, leading=14),
        "q_text":  s("q_text", fontSize=9.5, leading=13.5),
        "outreach": s("outreach", fontName=FONTS["sans_i"], fontSize=9.5, leading=14.5,
                      textColor=colors.HexColor("#5a4a40")),
    }


# ── Skill chips (greedy wrap into rows) ────────────────────────────────────────
def _chips(skills, max_w, size=8.5):
    rows, cur, cur_w = [], [], 0.0
    pad, gap = 9, 5
    font = FONTS["mono"]
    out = []
    for sk in skills:
        tw = pdfmetrics.stringWidth(sk, font, size) + 1.0 * max(0, len(sk) - 1)
        chip_w = tw + 2 * pad
        if cur and cur_w + chip_w + gap > max_w:
            rows.append(cur); cur, cur_w = [], 0.0
        cur.append((sk, chip_w)); cur_w += chip_w + gap
    if cur:
        rows.append(cur)

    for row in rows:
        cells, widths = [], []
        for sk, w in row:
            chip = Table([[MonoLabel(sk, size=size, color=colors.HexColor("#5a5852"), tracking=1.0)]],
                         colWidths=[w])
            chip.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), CHIP_BG),
                ("BOX", (0, 0), (-1, -1), 0.5, RULE),
                ("ROUNDEDCORNERS", [3, 3, 3, 3]),
                ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
            ]))
            cells.append(chip); widths.append(w + gap)
        rowtbl = Table([cells], colWidths=widths)
        rowtbl.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ]))
        out.append(rowtbl)
    return out


# ── Card: hairline box with a mono label header + content ──────────────────────
def _card(label, content, width, min_h=None, pad=12):
    rows = [[MonoLabel(label, size=7.5, color=MUTE, tracking=1.8)], [content]]
    t = Table(rows, colWidths=[width], rowHeights=[None, None])
    style = [
        ("BOX", (0, 0), (-1, -1), 0.8, RULE),
        ("LINEBELOW", (0, 0), (0, 0), 0.6, RULE),
        ("BACKGROUND", (0, 0), (-1, -1), CARD_BG),
        ("LEFTPADDING", (0, 0), (-1, -1), pad), ("RIGHTPADDING", (0, 0), (-1, -1), pad),
        ("TOPPADDING", (0, 0), (0, 0), 9), ("BOTTOMPADDING", (0, 0), (0, 0), 7),
        ("TOPPADDING", (0, 1), (0, 1), 10), ("BOTTOMPADDING", (0, 1), (0, 1), 12),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    t.setStyle(TableStyle(style))
    return t


def _kv_table(pairs, width, styles):
    """Label/value rows with dotted hairline separators (KEY FACTS)."""
    data, n = [], len(pairs)
    for lbl, val in pairs:
        data.append([MonoLabel(lbl.upper(), size=7, color=MUTE, tracking=1.4),
                     Paragraph(val, styles["kv_val"])])
    t = Table(data, colWidths=[width * 0.36, width * 0.64])
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]
    for i in range(n - 1):
        style.append(("LINEBELOW", (0, i), (-1, i), 0.4, FAINT))
    t.setStyle(TableStyle(style))
    return t


# ── Pentagon strength radar ─────────────────────────────────────────────────--
def _radar(labels, scores, size=160):
    d = Drawing(size, size)
    cx, cy, R = size / 2.0, size / 2.0 - 4, size * 0.30
    n = len(scores)
    angles = [math.radians(90 - i * (360.0 / n)) for i in range(n)]

    def pt(ang, r):
        return (cx + r * math.cos(ang), cy + r * math.sin(ang))

    scale = 100.0 if any((s or 0) > 10 for s in scores) else 10.0

    # grid rings
    for ring in (0.25, 0.5, 0.75, 1.0):
        pts = []
        for a in angles:
            x, y = pt(a, R * ring)
            pts += [x, y]
        d.add(Polygon(pts, strokeColor=RULE, strokeWidth=0.5, fillColor=None))
    # spokes
    for a in angles:
        x, y = pt(a, R)
        d.add(Line(cx, cy, x, y, strokeColor=RULE, strokeWidth=0.5))
    # data polygon
    dpts, verts = [], []
    for a, sc in zip(angles, scores):
        x, y = pt(a, R * max(0.0, min(1.0, (sc or 0) / scale)))
        dpts += [x, y]; verts.append((x, y))
    poly = Polygon(dpts, fillColor=ACCENT, strokeColor=ACCENT, strokeWidth=1.3)
    poly.fillOpacity = 0.17
    d.add(poly)
    for (x, y) in verts:
        d.add(Circle(x, y, 1.8, fillColor=ACCENT, strokeColor=WHITE, strokeWidth=0.5))
    # axis labels + scores
    for a, lbl, sc in zip(angles, labels, scores):
        lx, ly = pt(a, R + 16)
        anchor = "middle"
        if math.cos(a) > 0.3:
            anchor = "start"
        elif math.cos(a) < -0.3:
            anchor = "end"
        disp = int(round(max(0.0, min(1.0, (sc or 0) / scale)) * 10))
        d.add(String(lx, ly + 2, lbl.upper(), fontName=FONTS["mono"], fontSize=6,
                     fillColor=MUTE, textAnchor=anchor))
        d.add(String(lx, ly - 8, str(disp), fontName=FONTS["sans_b"], fontSize=9,
                     fillColor=INK, textAnchor=anchor))
    return d


# ── Horizontal strength bars (match detail / pipeline cards) ───────────────────
def _strength_bars(labels, scores, width, row_h=17, lbl_w=72, score_w=34,
                   show_labels=True, fill=INK):
    n = len(scores)
    H = n * row_h
    d = Drawing(width, H)
    bx = lbl_w if show_labels else 0
    bw = width - bx - score_w
    scale = 100.0 if any((s or 0) > 10 for s in scores) else 10.0
    for i, (lbl, sc) in enumerate(zip(labels, scores)):
        y = H - (i + 1) * row_h + (row_h - 8) / 2.0
        ratio = max(0.0, min(1.0, (sc or 0) / scale))
        disp = int(round(ratio * 10))
        if show_labels:
            d.add(String(0, y + 0.5, lbl, fontName=FONTS["sans"], fontSize=8.5,
                         fillColor=colors.HexColor("#3a3a36"), textAnchor="start"))
        d.add(Rect(bx, y, bw, 7, fillColor=TRACK, strokeColor=None))
        d.add(Rect(bx, y, ratio * bw, 7, fillColor=fill, strokeColor=None))
        d.add(String(bx + bw + score_w, y, str(disp), fontName=FONTS["sans_b"], fontSize=8.5,
                     fillColor=INK, textAnchor="end"))
        d.add(String(bx + bw + score_w + 1, y, "/10", fontName=FONTS["mono"], fontSize=6.5,
                     fillColor=MUTE, textAnchor="start"))
    return d


# ── Salary histogram with median / mean / this markers ─────────────────────────
def _salary_hist(this_sal, mean, median, count, width, height=68):
    d = Drawing(width, height)
    if not mean or mean <= 0:
        return d
    lo, hi = 0.0, max(mean, median or 0, this_sal or 0) * 1.6
    rng = hi - lo or 1.0
    bx, bw = 2.0, width - 4.0
    base_y, max_bar = 16.0, height - 34.0

    def px(v):
        return bx + max(0.0, min(1.0, (v - lo) / rng)) * bw

    # synthesize a right-skewed distribution centred near the mean
    nbars = 34
    mu = (mean - lo) / rng
    sigma = 0.16
    for i in range(nbars):
        t = (i + 0.5) / nbars
        val = math.exp(-((t - mu) ** 2) / (2 * sigma ** 2))
        bx_i = bx + t * bw
        bh = val * max_bar
        d.add(Rect(bx_i, base_y, bw / nbars * 0.7, max(0.6, bh),
                   fillColor=colors.HexColor("#D9D6CA"), strokeColor=None))
    d.add(Line(bx, base_y, bx + bw, base_y, strokeColor=RULE, strokeWidth=0.5))

    def marker(v, color, label, bold=False, dy=0.0, anchor="middle"):
        if not v:
            return
        x = px(v)
        d.add(Line(x, base_y - 2, x, base_y + max_bar + 2, strokeColor=color,
                   strokeWidth=1.4 if bold else 1.0))
        d.add(String(x, base_y + max_bar + 5 + dy, label, fontName=FONTS["mono"],
                     fontSize=5.8, fillColor=color, textAnchor=anchor))

    # stagger labels so close-together markers don't collide
    marker(median, MUTE2, "med", dy=0.0, anchor="end")
    marker(mean, colors.HexColor("#8a877d"), "mean", dy=7.0, anchor="end")
    marker(this_sal, ACCENT, "this", bold=True, dy=0.0, anchor="start")
    # x-axis end labels
    d.add(String(bx, 4, "€0", fontName=FONTS["mono"], fontSize=5.8,
                 fillColor=MUTE, textAnchor="start"))
    d.add(String(bx + bw, 4, f"€{hi/1000:.0f}k", fontName=FONTS["mono"], fontSize=5.8,
                 fillColor=MUTE, textAnchor="end"))
    return d


# ── Hexagon logo mark ──────────────────────────────────────────────────────────
def _hexagon_points(cx, cy, r):
    pts = []
    for i in range(6):
        a = math.radians(60 * i - 90)
        pts += [cx + r * math.cos(a), cy + r * math.sin(a)]
    return pts


# ── Austria opportunity map (real Bundesland geometry choropleth) ──────────────
# Short display names so labels fit inside the smaller states.
_AT_SHORT = {
    "NIEDERÖSTERREICH": "NIEDERÖST.", "OBERÖSTERREICH": "OBERÖST.",
    "VORARLBERG": "VBG.", "BURGENLAND": "BGLD.",
}

# Map common state spellings / English names onto the geometry keys.
_STATE_ALIASES = {
    "WIEN": "WIEN", "VIENNA": "WIEN",
    "NIEDERÖSTERREICH": "NIEDERÖSTERREICH", "NIEDEROESTERREICH": "NIEDERÖSTERREICH",
    "LOWER AUSTRIA": "NIEDERÖSTERREICH",
    "OBERÖSTERREICH": "OBERÖSTERREICH", "OBEROESTERREICH": "OBERÖSTERREICH",
    "UPPER AUSTRIA": "OBERÖSTERREICH",
    "STEIERMARK": "STEIERMARK", "STYRIA": "STEIERMARK",
    "KÄRNTEN": "KÄRNTEN", "KAERNTEN": "KÄRNTEN", "CARINTHIA": "KÄRNTEN",
    "TIROL": "TIROL", "TYROL": "TIROL",
    "SALZBURG": "SALZBURG", "VORARLBERG": "VORARLBERG", "BURGENLAND": "BURGENLAND",
}

_NODATA = colors.HexColor("#EDE8DE")  # a state with no matches


def _norm_state(s):
    """Map a job's free-text state onto an AT_POLYGONS key, or None."""
    key = (s or "").strip().upper()
    if not key:
        return None
    if key in _STATE_ALIASES:
        return _STATE_ALIASES[key]
    for k in AT_POLYGONS:
        if k == key or k in key or key in k:
            return k
    return None


def _market_stats(cand_jobs):
    """Aggregate the candidate's saved jobs by Bundesland (real per-export data)."""
    per = {}
    for j in cand_jobs:
        k = _norm_state(j.get("state"))
        if not k:
            continue
        d = per.setdefault(k, {"count": 0, "sal": [], "score": [],
                               "companies": [], "grades": []})
        d["count"] += 1
        sal = _to_num(j.get("salary"))
        if sal:
            d["sal"].append(sal)
        sc = _to_num(j.get("score"))
        if sc is not None:
            d["score"].append(sc)
        co = (j.get("company") or "").strip()
        if co and co not in d["companies"]:
            d["companies"].append(co)
        g = (j.get("grade") or "").strip().upper()
        if g:
            d["grades"].append(g)
    all_scores = [s for d in per.values() for s in d["score"]]
    if any((s or 0) > 10 for s in all_scores):
        scale = 100.0
    elif any((s or 0) > 1 for s in all_scores):
        scale = 10.0
    else:
        scale = 1.0
    return {
        "per": per, "scale": scale, "total": len(cand_jobs),
        "mapped": sum(d["count"] for d in per.values()),
        "n_states": len(per),
        "maxcount": max((d["count"] for d in per.values()), default=0),
    }


def _heat_color(count, maxcount):
    if count <= 0:
        return _NODATA
    if maxcount <= 0:
        return HEAT[2]
    frac = count / float(maxcount)
    if frac >= 0.66:
        return HEAT[0]
    if frac >= 0.33:
        return HEAT[1]
    return HEAT[2]


def _ring_centroid(ring):
    """Area-weighted centroid of a closed ring; falls back to vertex mean."""
    a = cx = cy = 0.0
    n = len(ring)
    for i in range(n):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % n]
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if abs(a) < 1e-6:
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        return sum(xs) / n, sum(ys) / n
    a *= 0.5
    return cx / (6 * a), cy / (6 * a)


def _austria_map(width, counts, maxcount, height=210):
    d = Drawing(width, height)
    # fit geometry, preserve aspect ratio, centre in the drawing
    scale = min(width / AT_WIDTH, (height - 4) / AT_HEIGHT)
    ox = (width - AT_WIDTH * scale) / 2.0
    oy = (height - AT_HEIGHT * scale) / 2.0

    def S(x, y):
        return (ox + x * scale, oy + y * scale)

    # fill each state's rings by match count
    for name, rings in AT_POLYGONS.items():
        col = _heat_color(counts.get(name, 0), maxcount)
        for ring in rings:
            pts = []
            for (x, y) in ring:
                sx_, sy_ = S(x, y)
                pts += [sx_, sy_]
            d.add(Polygon(pts, fillColor=col, strokeColor=PAPER, strokeWidth=1.1))

    # labels (name + count) placed at the largest ring's centroid
    for name, rings in AT_POLYGONS.items():
        biggest = max(rings, key=len)
        cx, cy = _ring_centroid(biggest)
        px, py = S(cx, cy)
        v = counts.get(name, 0)
        has = v > 0
        frac = (v / float(maxcount)) if maxcount else 0
        if name == "WIEN":
            # tiny — mark with a dot, label to the upper-right with a leader line
            dot_col = INK if has else colors.HexColor("#B9B2A4")
            d.add(Circle(px, py, 2.0, fillColor=dot_col, strokeColor=WHITE, strokeWidth=0.6))
            lx, ly = px + 9, py + 9
            d.add(Line(px + 1.6, py + 1.6, lx - 1, ly - 1, strokeColor=dot_col, strokeWidth=0.5))
            d.add(String(lx, ly, "WIEN", fontName=FONTS["mono"], fontSize=5,
                         fillColor=(INK if has else colors.HexColor("#9A9384")),
                         textAnchor="start"))
            if has:
                d.add(String(lx, ly - 6, f"{v:,}", fontName=FONTS["sans_b"], fontSize=7.5,
                             fillColor=INK, textAnchor="start"))
            continue
        disp = _AT_SHORT.get(name, name)
        if has:
            tcol = WHITE if frac >= 0.66 else colors.HexColor("#7a4a2e")
            d.add(String(px, py + 2, disp, fontName=FONTS["mono"], fontSize=5,
                         fillColor=tcol, textAnchor="middle"))
            d.add(String(px, py - 6, f"{v:,}", fontName=FONTS["sans_b"], fontSize=7.5,
                         fillColor=tcol, textAnchor="middle"))
        else:
            d.add(String(px, py, disp, fontName=FONTS["mono"], fontSize=4.6,
                         fillColor=colors.HexColor("#A89F8E"), textAnchor="middle"))
    return d


# ── Header / footer page furniture ─────────────────────────────────────────────
def _make_page_decorator(today_str, page_meta, totals):
    def decorate(canvas: Canvas, doc):
        canvas.saveState()
        # paper background
        canvas.setFillColor(PAPER)
        canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

        top_y = PAGE_H - 1.45 * cm
        # logo placeholder (dashed box + hexagon)
        bx, by, bw, bh = MARGIN_X, top_y - 6, 3.05 * cm, 0.74 * cm
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.7)
        canvas.setDash(2, 2)
        canvas.roundRect(bx, by, bw, bh, 3, fill=0, stroke=1)
        canvas.setDash()
        hx, hy = bx + 16, by + bh / 2
        canvas.setStrokeColor(ACCENT)
        canvas.setLineWidth(1.1)
        pts = _hexagon_points(hx, hy, 5.2)
        canvas.lines([(pts[i], pts[i + 1], pts[(i + 2) % 12], pts[(i + 3) % 12])
                      for i in range(0, 12, 2)])
        _ls(canvas, bx + 30, by + bh / 2 - 3, "YOUR LOGO", FONTS["mono"], 8, MUTE, 1.6)

        # right header meta
        _ls(canvas, PAGE_W - MARGIN_X, top_y - 3,
            f"JOBS INTELLIGENCE · CANDIDATE PIPELINE REPORT   {today_str.upper()}",
            FONTS["mono"], 8, MUTE, 1.4, anchor="r")
        # header rule
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.6)
        canvas.line(MARGIN_X, top_y - 16, PAGE_W - MARGIN_X, top_y - 16)

        # footer
        meta = page_meta.get(doc.page, {})
        foot_y = 1.15 * cm
        canvas.setStrokeColor(RULE)
        canvas.line(MARGIN_X, foot_y + 12, PAGE_W - MARGIN_X, foot_y + 12)
        _ls(canvas, MARGIN_X, foot_y, meta.get("foot_left", ""), FONTS["mono"], 7, MUTE, 1.3)
        _ls(canvas, PAGE_W / 2, foot_y, meta.get("section", ""), FONTS["mono"], 7, MUTE, 1.6, anchor="c")
        _ls(canvas, PAGE_W - MARGIN_X, foot_y,
            f"{doc.page} / {totals['n']}", FONTS["mono"], 7, MUTE, 1.3, anchor="r")
        canvas.restoreState()
    return decorate


class _SectionMark(Flowable):
    """Zero-height flowable that records the section label + footer-left for its page."""
    def __init__(self, page_meta, section, foot_left):
        Flowable.__init__(self)
        self.page_meta = page_meta
        self.section = section
        self.foot_left = foot_left

    def wrap(self, *a):
        return (0, 0)

    def draw(self):
        self.page_meta[self.canv.getPageNumber()] = {
            "section": self.section, "foot_left": self.foot_left,
        }


# ── helpers ────────────────────────────────────────────────────────────────────
def _to_num(val):
    try:
        return float(str(val).replace(",", "").replace("€", "").replace(".", "", 0).strip())
    except Exception:
        return None


def _money(v):
    try:
        return f"€{int(round(float(v))):,}"
    except Exception:
        return "—"


def _short_radar_labels(axes):
    out = []
    for a in axes:
        out.append((a or "").split()[0][:10])
    return out


def _initials(name):
    parts = [p for p in (name or "").split() if p]
    return ("".join(p[0] for p in parts[:2]) or "?").upper()


def _cand_id(name):
    init = _initials(name)
    num = abs(hash(name or "")) % 100000
    return f"{init}-{num:05d}"


def _days_old(posted):
    try:
        d = datetime.fromisoformat(str(posted)[:10]).date()
        return (date.today() - d).days
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════════════════════
# PAGE BUILDERS
# ════════════════════════════════════════════════════════════════════════════════
def _build_dossier(story, ST, cand_name, prof, cand_jobs, page_meta, foot_left):
    story.append(_SectionMark(page_meta, "CANDIDATE DOSSIER", foot_left))

    cid = _cand_id(cand_name)
    # ── identity row: avatar + eyebrow + name + sub
    init = _initials(cand_name)
    avatar = Table([[Paragraph(init, ParagraphStyle("av", fontName=FONTS["sans_b"],
                    fontSize=19, textColor=WHITE, alignment=TA_CENTER, leading=22))]],
                   colWidths=[54], rowHeights=[54])
    avatar.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), INK),
        ("ROUNDEDCORNERS", [27, 27, 27, 27]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    eyebrow = f"CANDIDATE DOSSIER · {cid}"
    exp = prof.get("experience_years")
    sub_parts = [prof.get("title"), prof.get("location"),
                 (f"{exp} experience" if exp and "exp" not in str(exp).lower() else exp)]
    sub = "  ·  ".join(p for p in sub_parts if p)
    name_block = [MonoLabel(eyebrow, size=8, color=MUTE, tracking=1.6, space_after=4),
                  Paragraph(cand_name, ST["name"])]
    if sub:
        name_block.append(Spacer(1, 2))
        name_block.append(Paragraph(sub, ST["sub"]))

    idrow = Table([[avatar, name_block]], colWidths=[68, COL_W - 68])
    idrow.setStyle(TableStyle([
        ("VALIGN", (0, 0), (0, 0), "TOP"), ("VALIGN", (1, 0), (1, 0), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, 0), 0), ("LEFTPADDING", (1, 0), (1, 0), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story += [Spacer(1, 4), idrow, Spacer(1, 12),
              HRFlowable(width="100%", thickness=0.6, color=RULE), Spacer(1, 14)]

    # ── two columns: profile summary | key facts
    gap = 18
    left_w = (COL_W - gap) * 0.54
    right_w = (COL_W - gap) * 0.46

    left_content = []
    if prof.get("summary"):
        left_content.append(Paragraph(prof["summary"], ST["body"]))
    skills = prof.get("skills") or []
    if skills:
        left_content.append(Spacer(1, 8))
        left_content.append(HRFlowable(width="100%", thickness=0.4, color=FAINT,
                                        dash=(1, 2)))
        left_content.append(Spacer(1, 8))
        left_content.extend(_chips(skills[:14], left_w - 24))
    left_card = _card("PROFILE SUMMARY", left_content, left_w)

    kv = []
    for lbl, key in [("Languages", "languages"), ("Salary", "salary_expectation"),
                     ("Availability", "availability"), ("Education", "education"),
                     ("Location", "location")]:
        v = prof.get(key)
        if v:
            kv.append((lbl, v))
    right_card = _card("KEY FACTS", _kv_table(kv, right_w - 24, ST) if kv
                       else Paragraph("—", ST["body"]), right_w)

    cols = Table([[left_card, right_card]], colWidths=[left_w, right_w])
    cols.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, 0), 0), ("RIGHTPADDING", (0, 0), (0, 0), gap),
        ("LEFTPADDING", (1, 0), (1, 0), 0), ("RIGHTPADDING", (1, 0), (1, 0), 0),
    ]))
    story += [cols, Spacer(1, 14)]

    # ── candidate strength profile (radar + list + verdict)
    strengths = [j.get("extras", {}).get("strength") for j in cand_jobs
                 if j.get("extras", {}).get("strength")]
    strengths = [s for s in strengths if s and s.get("axes") and s.get("scores")]
    if strengths:
        # representative = top job (grade A / highest score) for reasons+verdict
        def jscore(j):
            return (1 if (j.get("grade") or "C").upper() == "A" else 0,
                    j.get("score") or 0)
        top_job = max(cand_jobs, key=jscore)
        rep = top_job.get("extras", {}).get("strength") or strengths[0]
        axes = rep.get("axes")
        # candidate-level scores = average across jobs (aligned by index)
        nax = len(axes)
        avg = []
        for i in range(nax):
            vals = [s["scores"][i] for s in strengths
                    if len(s.get("scores", [])) > i and isinstance(s["scores"][i], (int, float))]
            avg.append(round(sum(vals) / len(vals)) if vals else 0)
        reasons = rep.get("reasons") or [""] * nax
        overall = rep.get("overall") or ""

        radar = _radar(_short_radar_labels(axes), avg, size=168)

        scale = 100.0 if any((s or 0) > 10 for s in avg) else 10.0
        rows = []
        for ax, sc, rsn in zip(axes, avg, reasons):
            disp = int(round(max(0.0, min(1.0, (sc or 0) / scale)) * 10))
            rows.append([
                Paragraph(f'<b>{ax}</b>', ParagraphStyle("ax", fontName=FONTS["sans"],
                          fontSize=9.5, textColor=INK, leading=12)),
                Paragraph(f'<font name="{FONTS["sans_b"]}">{disp}</font>'
                          f'<font name="{FONTS["mono"]}" size="7" color="#9a9890">/10</font>',
                          ParagraphStyle("sc", fontSize=9.5, leading=12, alignment=TA_LEFT)),
                Paragraph(rsn or "", ParagraphStyle("rs", fontName=FONTS["sans"],
                          fontSize=8.5, textColor=colors.HexColor("#54524b"), leading=11.5)),
            ])
        list_w = COL_W - 188
        rtbl = Table(rows, colWidths=[list_w * 0.30, list_w * 0.12, list_w * 0.58])
        rtbl.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        for i in range(len(rows) - 1):
            rtbl.setStyle(TableStyle([("LINEBELOW", (0, i), (-1, i), 0.4, FAINT)]))

        body = Table([[radar, rtbl]], colWidths=[188, COL_W - 188 - 24])
        body.setStyle(TableStyle([
            ("VALIGN", (0, 0), (0, 0), "MIDDLE"), ("VALIGN", (1, 0), (1, 0), "TOP"),
            ("LEFTPADDING", (0, 0), (0, 0), 4), ("LEFTPADDING", (1, 0), (1, 0), 14),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
        ]))
        content = [body]
        if overall:
            content += [Spacer(1, 8), _verdict_band(overall, COL_W - 24, ST)]
        story.append(_card("CANDIDATE STRENGTH PROFILE", content, COL_W))


def _verdict_band(text, width, ST):
    t = Table([["", Paragraph(text, ST["italic"])]], colWidths=[4, width - 4])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), ACCENT),
        ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#F2EFE7")),
        ("LEFTPADDING", (0, 0), (0, 0), 0), ("RIGHTPADDING", (0, 0), (0, 0), 0),
        ("LEFTPADDING", (1, 0), (1, 0), 11), ("RIGHTPADDING", (1, 0), (1, 0), 11),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def _build_market(story, ST, cand_jobs, page_meta, foot_left):
    story.append(PageBreak())
    story.append(_SectionMark(page_meta, "MARKET ANALYSIS · AUSTRIA", foot_left))

    stats = _market_stats(cand_jobs)
    per = stats["per"]
    counts = {k: v["count"] for k, v in per.items()}
    total = stats["total"]
    n_states = stats["n_states"]
    unit = "Bundesland" if n_states == 1 else "Bundesländer"
    if n_states:
        headline = (f"{total} saved role{'s' if total != 1 else ''} across "
                    f"{n_states} {unit}")
    else:
        headline = f"{total} saved role{'s' if total != 1 else ''}"
    sub = ("Geographic distribution of the candidate's saved matches across Austria. "
           "Heat by number of matches per Bundesland.")

    story += [MonoLabel("MARKET ANALYSIS · AUSTRIA · SAVED MATCHES", size=8,
                        color=MUTE, tracking=1.6, space_after=6),
              Paragraph(headline, ST["h1"]), Spacer(1, 3),
              Paragraph(sub, ST["sub"]), Spacer(1, 10),
              HRFlowable(width="100%", thickness=0.5, color=RULE), Spacer(1, 12),
              MonoLabel("OPPORTUNITY MAP · PER BUNDESLAND", size=7.5, color=MUTE,
                        tracking=1.7, space_after=8)]

    # map + callouts (top states by match count)
    map_w = COL_W * 0.62
    call_w = COL_W - map_w - 16
    ranked_states = sorted(per.items(), key=lambda kv: kv[1]["count"], reverse=True)[:3]
    callout_flows = []
    if ranked_states:
        for i, (name, d) in enumerate(ranked_states):
            avg_sal = sum(d["sal"]) / len(d["sal"]) if d["sal"] else None
            mq = (sum(d["score"]) / len(d["score"]) / stats["scale"] * 100) if d["score"] else None
            cnt = d["count"]
            eyebrow = _AT_SHORT.get(name, name) + (" · TOP" if i == 0 else "")
            inner = [MonoLabel(eyebrow, size=6.8, color=ACCENT, tracking=1.3, space_after=3),
                     Paragraph(f"{cnt} match{'es' if cnt != 1 else ''}",
                               ParagraphStyle("co_big", fontName=FONTS["sans_b"],
                               fontSize=12, textColor=INK, leading=15))]
            facts = []
            if avg_sal:
                facts.append(f"{_money(avg_sal)} avg")
            if mq is not None:
                facts.append(f"{mq:.0f}% match quality")
            if facts:
                inner.append(Paragraph(" · ".join(facts),
                             ParagraphStyle("co_l", fontName=FONTS["sans"],
                             fontSize=7.5, textColor=MUTE2, leading=10.5, spaceBefore=2)))
            if d["companies"]:
                inner.append(Paragraph(" · ".join(d["companies"][:3]),
                             ParagraphStyle("co_c", fontName=FONTS["sans"], fontSize=7.5,
                             textColor=MUTE2, leading=10.5, spaceBefore=2)))
            box = Table([[inner]], colWidths=[call_w])
            box.setStyle(TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#E7C9B6")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FBF1EA")),
                ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ]))
            callout_flows.append(box)
            if i < len(ranked_states) - 1:
                callout_flows.append(Spacer(1, 8))
    else:
        callout_flows.append(Paragraph(
            "No geographic data available for the saved roles.",
            ParagraphStyle("nd", fontName=FONTS["sans"], fontSize=8.5,
                           textColor=MUTE2, leading=12)))

    map_draw = _austria_map(map_w, counts, stats["maxcount"], height=215)
    map_row = Table([[map_draw, callout_flows]], colWidths=[map_w, COL_W - map_w])
    map_row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (0, 0), "MIDDLE"), ("VALIGN", (1, 0), (1, 0), "TOP"),
        ("LEFTPADDING", (0, 0), (0, 0), 0), ("LEFTPADDING", (1, 0), (1, 0), 16),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story += [map_row, Spacer(1, 8)]

    # legend (relative heat — matches per state)
    legend = Table([[
        MonoLabel("HEAT · MATCHES / STATE", size=6.8, color=MUTE, tracking=1.3),
        _legend_swatch("MOST", HEAT[0]),
        _legend_swatch("MEDIUM", HEAT[1]),
        _legend_swatch("FEWEST", HEAT[2]),
        _legend_swatch("NONE", _NODATA),
        _legend_swatch("WIEN", INK, dot=True),
    ]], colWidths=[COL_W * 0.26, COL_W * 0.12, COL_W * 0.15, COL_W * 0.15,
                   COL_W * 0.13, COL_W * 0.19])
    legend.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story += [legend, Spacer(1, 14),
              HRFlowable(width="100%", thickness=0.5, color=RULE), Spacer(1, 12),
              MonoLabel("REGIONAL BREAKDOWN", size=7.5, color=MUTE, tracking=1.7,
                        space_after=8)]

    story.append(_market_table(ST, stats))


def _legend_swatch(label, color, dot=False):
    if dot:
        d = Drawing(10, 8)
        d.add(Circle(5, 4, 2.4, fillColor=color, strokeColor=None))
    else:
        d = Drawing(12, 8)
        d.add(Rect(0, 1, 11, 7, fillColor=color, strokeColor=None))
    t = Table([[d, MonoLabel(label, size=6.5, color=MUTE2, tracking=1.0)]],
              colWidths=[16, None])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def _market_table(ST, stats):
    headers = ["BUNDESLAND", "MATCHES", "AVG SALARY", "MATCH QUALITY", "TOP HIRING"]
    cw = [COL_W * 0.17, COL_W * 0.11, COL_W * 0.15, COL_W * 0.15, COL_W * 0.42]
    right = (1, 2, 3)
    data = [[MonoLabel(h, size=6.5, color=MUTE, tracking=1.0,
                       anchor="r" if i in right else "l") for i, h in enumerate(headers)]]

    def cell(t, **k):
        opts = dict(fontName=FONTS["sans"], fontSize=8.5, textColor=INK, leading=11)
        opts.update(k)
        return Paragraph(t, ParagraphStyle("c", **opts))

    per = stats["per"]
    rows = sorted(per.items(), key=lambda kv: kv[1]["count"], reverse=True)
    all_sal, all_sc = [], []
    for name, d in rows:
        avg_sal = sum(d["sal"]) / len(d["sal"]) if d["sal"] else None
        mq = (sum(d["score"]) / len(d["score"]) / stats["scale"] * 100) if d["score"] else None
        all_sal += d["sal"]
        all_sc += d["score"]
        disp = name.capitalize()
        hiring = ", ".join(d["companies"][:3]) if d["companies"] else "—"
        data.append([
            cell(f'<b>{disp}</b>'),
            cell(str(d["count"]), alignment=TA_RIGHT),
            cell(_money(avg_sal) if avg_sal else "—", alignment=TA_RIGHT, textColor=MUTE2),
            cell(f"{mq:.0f}%" if mq is not None else "—", alignment=TA_RIGHT),
            cell(hiring, fontSize=8, textColor=MUTE2, leading=10.5),
        ])
    # total row
    tot_sal = sum(all_sal) / len(all_sal) if all_sal else None
    tot_mq = (sum(all_sc) / len(all_sc) / stats["scale"] * 100) if all_sc else None
    data.append([
        Paragraph('<b>AUSTRIA TOTAL</b>', ParagraphStyle("tot", fontName=FONTS["sans_b"],
                  fontSize=8.5, textColor=INK, leading=11)),
        cell(str(stats["mapped"]), alignment=TA_RIGHT),
        cell(_money(tot_sal) if tot_sal else "—", alignment=TA_RIGHT, textColor=MUTE),
        cell(f"{tot_mq:.0f}%" if tot_mq is not None else "—", alignment=TA_RIGHT, textColor=MUTE),
        cell(""),
    ])
    t = Table(data, colWidths=cw)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, RULE),
        ("LINEBELOW", (0, -2), (-1, -2), 0.6, RULE),
        ("TOPPADDING", (0, -1), (-1, -1), 8),
    ]
    for i in range(1, len(rows)):
        style.append(("LINEBELOW", (0, i), (-1, i), 0.3, FAINT))
    t.setStyle(TableStyle(style))
    return t


def _fit_block(score_pct, salary):
    fit = Paragraph(
        f'<font name="{FONTS["sans_b"]}" size="21">{score_pct.replace("%","")}</font>'
        f'<font name="{FONTS["sans_b"]}" size="11">%</font>',
        ParagraphStyle("fit", alignment=TA_RIGHT, leading=22, textColor=INK))
    sub = [MonoLabel("FIT", size=6.5, color=MUTE, tracking=2.0, anchor="r")]
    if salary:
        sub.append(Paragraph(salary, ParagraphStyle("sal", fontName=FONTS["sans"],
                   fontSize=9, textColor=MUTE2, alignment=TA_RIGHT, leading=12, spaceBefore=3)))
    return [fit] + sub


def _grade_square(grade, size=24):
    col = GRADE_COLOR.get(grade, MUTE)
    g = Table([[Paragraph(grade, ParagraphStyle("g", fontName=FONTS["sans_b"],
              fontSize=12, textColor=WHITE, alignment=TA_CENTER, leading=14))]],
              colWidths=[size], rowHeights=[size])
    g.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), col), ("ROUNDEDCORNERS", [3, 3, 3, 3]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return g


def _new_tag():
    t = Table([[MonoLabel("NEW", size=6.5, color=ACCENT, tracking=1.0)]], colWidths=[26])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), ACCENT_HL), ("ROUNDEDCORNERS", [2, 2, 2, 2]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def _match_card(job, rank, width, ST):
    grade = (job.get("grade") or "C").upper()
    score_pct = job.get("score_pct") or (f"{round(job['score']*100)}%" if job.get("score") else "—")
    is_new = (job.get("pipeline_status") or "New") == "New"
    inner_w = width - 24

    # header: grade + RANK n + NEW ............. fit%
    hdr_left = Table([[_grade_square(grade, 22),
                       MonoLabel(f"RANK {rank}", size=7, color=MUTE2, tracking=1.4),
                       _new_tag() if is_new else Spacer(0, 0)]],
                     colWidths=[26, 56, 30])
    hdr_left.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                  ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                  ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                                  ("TOPPADDING", (0, 0), (-1, -1), 0),
                                  ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    fit = Paragraph(f'<font name="{FONTS["sans_b"]}" size="16">{score_pct.replace("%","")}</font>'
                    f'<font name="{FONTS["mono"]}" size="9">%</font>',
                    ParagraphStyle("f", alignment=TA_RIGHT, leading=18))
    header = Table([[hdr_left, fit]], colWidths=[inner_w - 70, 70])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                ("TOPPADDING", (0, 0), (-1, -1), 0),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))

    loc = ", ".join(filter(None, [job.get("city"), job.get("state")]))
    meta_parts = list(filter(None, [job.get("company"), loc,
                     (f"€{job['salary']} / yr" if job.get("salary") else None)]))
    content = [header, Spacer(1, 8),
               Paragraph(job.get("title") or "—", ST["match_ttl"]), Spacer(1, 3),
               Paragraph(" · ".join(meta_parts), ParagraphStyle("m", fontName=FONTS["mono"],
                         fontSize=7.5, textColor=MUTE2, leading=11))]

    st = job.get("extras", {}).get("strength")
    if st and st.get("axes") and st.get("scores"):
        content += [Spacer(1, 8), HRFlowable(width="100%", thickness=0.4, color=FAINT),
                    Spacer(1, 6),
                    _strength_bars(_short_radar_labels(st["axes"]), st["scores"],
                                   width - 24, row_h=15, lbl_w=58, score_w=30)]
    card = Table([[content]], colWidths=[width])
    card.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, RULE), ("BACKGROUND", (0, 0), (-1, -1), CARD_BG),
        ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 12), ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return card


def _build_pipeline(story, ST, cand_name, cand_jobs, page_meta, foot_left,
                    has_details=True):
    story.append(PageBreak())
    story.append(_SectionMark(page_meta, "PIPELINE OVERVIEW", foot_left))

    total = len(cand_jobs)
    grade_a = sum(1 for j in cand_jobs if (j.get("grade") or "C").upper() == "A")
    grade_b = sum(1 for j in cand_jobs if (j.get("grade") or "C").upper() == "B")
    sals = [_to_num(j.get("salary")) for j in cand_jobs]
    sals = [s for s in sals if s]
    if len(sals) >= 2:
        srange = f"€{min(sals)/1000:.1f}–{max(sals)/1000:.1f}k"
    elif sals:
        srange = f"€{sals[0]/1000:.1f}k"
    else:
        srange = "—"

    first = cand_jobs[0].get("title") if cand_jobs else ""
    story += [MonoLabel(f"PIPELINE · {cand_name.upper()}", size=8, color=MUTE,
                        tracking=1.6, space_after=6),
              Paragraph(f"{total} match{'es' if total != 1 else ''} in pipeline", ST["h1"]),
              Spacer(1, 3),
              Paragraph("Roles sourced and ranked against the candidate's profile."
                        + (" Each match is detailed on the following pages."
                           if has_details else ""), ST["sub"]),
              Spacer(1, 14)]

    # KPI card
    kpis = [(str(total), "JOBS SAVED", INK), (str(grade_a), "GRADE A MATCHES", INK),
            (str(grade_b), "GRADE B MATCHES", INK), (srange, "SALARY RANGE", INK)]
    kpi_cells = []
    for val, lbl, col in kpis:
        fs = 24 if len(val) <= 4 else 17
        kpi_cells.append([
            Paragraph(val, ParagraphStyle("kn", fontName=FONTS["sans_b"], fontSize=fs,
                      textColor=col, leading=fs + 2)),
            Spacer(1, 4),
            MonoLabel(lbl, size=6.8, color=MUTE, tracking=1.2),
        ])
    kpi_inner = Table([[ [c] for c in kpi_cells ]], colWidths=[(COL_W - 24) / 4] * 4)
    # flatten: each cell is list-of-flowables
    kpi_inner = Table([kpi_cells], colWidths=[(COL_W - 24) / 4] * 4)
    kpi_inner.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, 0), 0), ("LEFTPADDING", (1, 0), (-1, -1), 14),
        ("LINEAFTER", (0, 0), (-2, -1), 0.4, FAINT),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story += [_card("PIPELINE KPIS", kpi_inner, COL_W), Spacer(1, 14)]

    # ranked match cards (2-up)
    ranked = sorted(cand_jobs, key=lambda j: j.get("score") or 0, reverse=True)
    cards = [_match_card(j, i + 1, (COL_W - 16) / 2, ST) for i, j in enumerate(ranked)]
    matches_inner = []
    for i in range(0, len(cards), 2):
        pair = cards[i:i + 2]
        if len(pair) == 1:
            pair.append(Spacer((COL_W - 16) / 2, 0))
        row = Table([pair], colWidths=[(COL_W - 16) / 2, (COL_W - 16) / 2])
        row.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (0, 0), 0), ("RIGHTPADDING", (0, 0), (0, 0), 16),
            ("LEFTPADDING", (1, 0), (1, 0), 0), ("RIGHTPADDING", (1, 0), (1, 0), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        matches_inner.append(row)
    story.append(_card("MATCHES · RANKED BY FIT", matches_inner, COL_W))


def _build_match_detail(story, ST, job, match_no, page_meta, foot_left):
    story.append(PageBreak())
    story.append(_SectionMark(page_meta, f"MATCH #{match_no}", foot_left))

    ex = job.get("extras") or {}
    grade = (job.get("grade") or "C").upper()
    score_pct = job.get("score_pct") or (f"{round(job['score']*100)}%" if job.get("score") else "—")
    is_new = (job.get("pipeline_status") or "New") == "New"

    # ── header: grade + RANK + NEW row, eyebrow, title, company | fit + salary
    rank_row = Table([[_grade_square(grade, 26),
                       MonoLabel(f"RANK {match_no}", size=7, color=MUTE2, tracking=1.4),
                       _new_tag() if is_new else Spacer(0, 0)]],
                     colWidths=[30, 56, 30])
    rank_row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                  ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                  ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                                  ("TOPPADDING", (0, 0), (-1, -1), 0),
                                  ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))

    days = _days_old(job.get("posted"))
    domain = ""
    if job.get("url"):
        u = job["url"].replace("https://", "").replace("http://", "").replace("www.", "")
        domain = u.split("/")[0].upper()
    eb_parts = list(filter(None, [
        (f"POSTED {str(job['posted'])[:10]}" if job.get("posted") else None),
        (f"{days} DAYS OLD" if days is not None else None),
        domain or job.get("portal", ""),
    ]))
    loc = ", ".join(filter(None, [job.get("city"), job.get("state")]))

    left = [rank_row, Spacer(1, 8),
            MonoLabel(" · ".join(eb_parts), size=6.8, color=MUTE, tracking=1.3,
                      space_after=4) if eb_parts else Spacer(0, 0),
            Paragraph(job.get("title") or "—", ST["job_ttl"]), Spacer(1, 3),
            Paragraph(" · ".join(filter(None, [job.get("company"), loc])),
                      ParagraphStyle("co", fontName=FONTS["mono"], fontSize=8,
                                     textColor=MUTE2, leading=12))]
    fit_cell = _fit_block(score_pct, f"€{job['salary']} / yr" if job.get("salary") else None)
    hdr = Table([[left, fit_cell]], colWidths=[COL_W - 110, 110])
    hdr.setStyle(TableStyle([
        ("VALIGN", (0, 0), (0, 0), "TOP"), ("VALIGN", (1, 0), (1, 0), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story += [hdr, Spacer(1, 12), HRFlowable(width="100%", thickness=0.6, color=RULE),
              Spacer(1, 14)]

    # ── two columns
    gap = 22
    cw = (COL_W - gap) / 2.0
    left_col, right_col = [], []

    # LEFT: role summary
    if ex.get("compact"):
        left_col.append(_card("ROLE SUMMARY", Paragraph(ex["compact"], ST["body_s"]), cw))
        left_col.append(Spacer(1, 12))

    # LEFT: salary benchmark
    sv = ex.get("salary")
    if sv:
        this = sv.get("job_salary")
        pmkt = (f"P{100 - sv['pct_below']}" if sv.get("pct_below") is not None else None)
        sb_inner = []
        big_row = Table([[
            Paragraph(f"€{this/1000:.1f}k" if this else "—",
                      ParagraphStyle("sbn", fontName=FONTS["sans_b"], fontSize=19,
                                     textColor=INK, leading=22)),
            Paragraph(f'<font name="{FONTS["mono"]}" size="9" color="#C2410C">{pmkt} in market</font>'
                      if pmkt else "",
                      ParagraphStyle("pm", alignment=TA_RIGHT, leading=20)),
        ]], colWidths=[cw * 0.45, cw * 0.55 - 24])
        big_row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                                     ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                     ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                     ("TOPPADDING", (0, 0), (-1, -1), 0),
                                     ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
        sb_inner += [big_row,
                     MonoLabel("THIS POSTING", size=6.5, color=MUTE, tracking=1.4, space_before=2),
                     Spacer(1, 6),
                     _salary_hist(this, sv.get("mean"), sv.get("median"), sv.get("count"), cw - 24),
                     Spacer(1, 4),
                     MonoLabel(f"N = {sv['count']:,} COMPARABLE POSTINGS · SAME ROLE FAMILY"
                               if sv.get("count") else "COMPARABLE POSTINGS · SAME ROLE FAMILY",
                               size=6.3, color=MUTE, tracking=1.0)]
        left_col.append(_card("SALARY BENCHMARK", sb_inner, cw))
        left_col.append(Spacer(1, 12))

    # LEFT: posting quality
    q = ex.get("quality")
    if q:
        g_txt = {"high": "HIGH QUALITY", "mid": "MID QUALITY", "low": "LOW QUALITY"}.get(
            q.get("grade", ""), (q.get("grade", "") or "").upper())
        g_col = {"high": GREEN, "mid": ACCENT, "low": RED}.get(q.get("grade", ""), MUTE)
        score = q.get("score")
        pct = f"{int(score*100)}%" if isinstance(score, (int, float)) and score <= 1 else (
            f"{int(score)}%" if isinstance(score, (int, float)) else "—")
        big = Table([[Paragraph(f'<font name="{FONTS["sans_b"]}" size="20">{pct.replace("%","")}</font>'
                                f'<font name="{FONTS["mono"]}" size="10">%</font>',
                                ParagraphStyle("qp", leading=22)),
                      MonoLabel(g_txt, size=6.8, color=g_col, tracking=1.3)]],
                    colWidths=[52, cw - 24 - 52])
        big.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                 ("LEFTPADDING", (0, 0), (0, 0), 0),
                                 ("LEFTPADDING", (1, 0), (1, 0), 6),
                                 ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                 ("TOPPADDING", (0, 0), (-1, -1), 0),
                                 ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
        q_inner = [big]
        flags = q.get("flags") or []
        if flags:
            q_inner.append(Spacer(1, 6))
            for fl in flags:
                q_inner.append(_bullet(fl, cw - 24, ST))
        left_col.append(_card("POSTING QUALITY", q_inner, cw))

    # RIGHT: candidate strength
    st = ex.get("strength")
    if st and st.get("axes") and st.get("scores"):
        cs_inner = [_strength_bars(_short_radar_labels(st["axes"]), st["scores"],
                                   cw - 24, row_h=17, lbl_w=66, score_w=32)]
        if st.get("overall"):
            cs_inner += [Spacer(1, 8),
                         Paragraph(st["overall"], ST["body_s"])]
        right_col.append(_card("CANDIDATE STRENGTH", cs_inner, cw))
        right_col.append(Spacer(1, 12))

    # RIGHT: interview questions
    if ex.get("cv_questions"):
        qs = _split_questions(ex["cv_questions"])
        shown = qs[:5]
        more = len(qs) - len(shown)
        label = f"INTERVIEW QUESTIONS · {len(qs)}" if qs else "INTERVIEW QUESTIONS"
        iq_inner = []
        for i, qtext in enumerate(shown):
            iq_inner.append(_num_question(i + 1, qtext, cw - 24, ST))
            if i < len(shown) - 1:
                iq_inner += [Spacer(1, 5), HRFlowable(width="100%", thickness=0.3, color=FAINT),
                             Spacer(1, 5)]
        if more > 0:
            iq_inner += [Spacer(1, 7),
                         MonoLabel(f"+{more} MORE IN APPENDIX", size=6.5, color=MUTE, tracking=1.2)]
        right_col.append(_card(label, iq_inner, cw))
        right_col.append(Spacer(1, 12))

    # RIGHT: outreach draft
    if ex.get("outreach"):
        out_card = _card("OUTREACH DRAFT", _outreach_box(ex["outreach"], cw - 24, ST), cw)
        right_col.append(out_card)

    cols = Table([[left_col or [Spacer(0, 0)], right_col or [Spacer(0, 0)]]],
                 colWidths=[cw, cw])
    cols.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, 0), 0), ("RIGHTPADDING", (0, 0), (0, 0), gap),
        ("LEFTPADDING", (1, 0), (1, 0), 0), ("RIGHTPADDING", (1, 0), (1, 0), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(cols)


def _bullet(text, width, ST):
    t = Table([[Paragraph("•", ParagraphStyle("b", fontName=FONTS["sans"], fontSize=9,
               textColor=ACCENT, leading=12)),
               Paragraph(text, ParagraphStyle("bt", fontName=FONTS["sans"], fontSize=8.5,
               textColor=colors.HexColor("#54524b"), leading=11.5))]],
               colWidths=[12, width - 12])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                           ("TOPPADDING", (0, 0), (-1, -1), 2),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    return t


def _num_question(num, text, width, ST):
    t = Table([[Paragraph(text, ST["q_text"]),
                MonoLabel(f"{num:02d}", size=8, color=FAINT, tracking=0.5, anchor="r")]],
              colWidths=[width - 26, 26])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                           ("TOPPADDING", (0, 0), (-1, -1), 0),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return t


def _outreach_box(text, width, ST):
    inner = [Paragraph(text, ST["outreach"]), Spacer(1, 9)]
    btns = Table([[MonoLabel("COPY", size=7, color=MUTE2, tracking=1.2, anchor="c"),
                   Spacer(6, 0),
                   _send_btn()]],
                 colWidths=[60, 8, 90])
    btns.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                              ("BOX", (0, 0), (0, 0), 0.7, RULE),
                              ("ROUNDEDCORNERS", [3, 3, 3, 3]),
                              ("TOPPADDING", (0, 0), (0, 0), 5), ("BOTTOMPADDING", (0, 0), (0, 0), 5),
                              ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    inner.append(btns)
    box = Table([["", inner]], colWidths=[4, width - 4])
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), ACCENT),
        ("BACKGROUND", (1, 0), (1, 0), ACCENT_HL),
        ("LEFTPADDING", (0, 0), (0, 0), 0), ("RIGHTPADDING", (0, 0), (0, 0), 0),
        ("LEFTPADDING", (1, 0), (1, 0), 11), ("RIGHTPADDING", (1, 0), (1, 0), 11),
        ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return box


def _send_btn():
    t = Table([[MonoLabel("SEND VIA ATS", size=7, color=WHITE, tracking=1.2, anchor="c")]],
              colWidths=[90])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), ACCENT),
                           ("ROUNDEDCORNERS", [3, 3, 3, 3]),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    return t


def _split_questions(text):
    if isinstance(text, (list, tuple)):
        return [str(q).strip() for q in text if str(q).strip()]
    out = []
    for line in str(text).replace("\r", "").split("\n"):
        line = line.strip()
        if not line:
            continue
        # strip leading numbering "1." "1)" "- " "Q1:"
        import re
        line = re.sub(r"^\s*(?:Q?\d+[\.\)\:]|[-•])\s*", "", line)
        if line:
            out.append(line)
    return out


# ════════════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ════════════════════════════════════════════════════════════════════════════════
def generate_saved_jobs_pdf(jobs, candidate_profile=None):
    _register_fonts()
    ST = _styles()
    today_str = date.today().strftime("%b %d, %Y")

    # group by candidate
    groups = {}
    for j in jobs:
        groups.setdefault(j.get("candidate_name") or "Candidate", []).append(j)

    page_meta = {}
    totals = {"n": 0}

    def build_story():
        story = []
        for gi, (cand_name, cand_jobs) in enumerate(groups.items()):
            if gi > 0:
                story.append(PageBreak())
            prof = dict(candidate_profile or {})
            if prof.get("name") and cand_name and \
               prof["name"].lower() not in cand_name.lower() and \
               cand_name.lower() not in prof["name"].lower():
                prof = {}
            foot_left = f"{cand_name.upper()} · {_cand_id(cand_name)}"

            ranked = sorted(cand_jobs, key=lambda j: j.get("score") or 0, reverse=True)
            detailed = [j for j in ranked if any((j.get("extras") or {}).values())]

            _build_dossier(story, ST, cand_name, prof, cand_jobs, page_meta, foot_left)
            _build_market(story, ST, cand_jobs, page_meta, foot_left)
            _build_pipeline(story, ST, cand_name, cand_jobs, page_meta, foot_left,
                            has_details=bool(detailed))
            for mi, job in enumerate(detailed, 1):
                _build_match_detail(story, ST, job, mi, page_meta, foot_left)
        return story

    def make_doc(buf):
        doc = BaseDocTemplate(
            buf, pagesize=A4,
            leftMargin=MARGIN_X, rightMargin=MARGIN_X,
            topMargin=MARGIN_TOP, bottomMargin=MARGIN_BOT,
            title="Jobs Intelligence — Candidate Pipeline Report",
            author="Jobs Intelligence Austria",
        )
        frame = Frame(MARGIN_X, MARGIN_BOT, COL_W,
                      PAGE_H - MARGIN_TOP - MARGIN_BOT, id="main",
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        deco = _make_page_decorator(today_str, page_meta, totals)
        doc.addPageTemplates([PageTemplate(id="all", frames=[frame], onPage=deco)])
        return doc

    # pass 1: populate page_meta + page count
    doc1 = make_doc(io.BytesIO())
    doc1.build(build_story())
    totals["n"] = doc1.page

    # pass 2: real render with footers knowing the total
    out = io.BytesIO()
    make_doc(out).build(build_story())
    return out.getvalue()
