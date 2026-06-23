"""
helpers/report_generator.py — Analytics session report.

1. Sends saved items + briefing context to the LLM for elaboration.
2. Builds a professional PDF using reportlab, grouped into typed sections.

Requires: pip install reportlab
"""
import base64
import io
import json
import logging
from datetime import date

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable, Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    PageBreak, KeepTogether,
)
from reportlab.graphics.shapes import (
    Drawing, Rect, Line, String as GStr, Circle, Group,
)
from reportlab.graphics import renderPDF

from jobs_intelligence_ai import config
from jobs_intelligence_ai.shared.llm import get_client
from .config import ELABORATION_MODEL, ELABORATION_PROMPT, ElaborationList

logger = logging.getLogger(__name__)

PAGE_W, PAGE_H = A4
MARGIN = 2.5 * cm
COL_W = PAGE_W - 2 * MARGIN

# ── Palette ───────────────────────────────────────────────────────────────────
NAVY   = colors.HexColor("#1a3864")
BLUE   = colors.HexColor("#1a56c4")
LIGHT  = colors.HexColor("#f5f8ff")
BORDER = colors.HexColor("#dce8fb")
DIVIDER= colors.HexColor("#e0dfd8")
GREY   = colors.HexColor("#6b7280")
DARK   = colors.HexColor("#1a1a18")
WHITE  = colors.white

TYPE_COLORS = {
    "recommendation": "#1a56c4",
    "opportunity":    "#16a34a",
    "underserved":    "#d97706",
    "urgency":        "#ea580c",
    "trend":          "#7c3aed",
    "chat":           "#6b7280",
}
TYPE_LABELS = {
    "recommendation": "RECOMMENDATION",
    "opportunity":    "TOP OPPORTUNITY",
    "underserved":    "UNDERSERVED MARKET",
    "urgency":        "URGENCY ALERT",
    "trend":          "TREND INSIGHT",
    "chat":           "CHAT INSIGHT",
}

SECTION_ORDER = ["recommendation", "opportunity", "underserved", "urgency", "trend", "chat"]
SECTION_NAMES = {
    "recommendation": "Recommendations",
    "opportunity":    "Top Opportunities",
    "underserved":    "Underserved Markets",
    "urgency":        "Urgency Alerts",
    "trend":          "Trend Insights",
    "chat":           "Chat Insights",
}

# ── AI elaboration ────────────────────────────────────────────────────────────

def elaborate_items(items: list[dict], context: dict) -> list[dict]:
    """Ask the LLM to elaborate each item (Structured Outputs). Returns the merged list
    with heading / elaboration / action_steps fields; falls back to a plain copy of each
    item on missing key, empty input, or any model failure."""
    if not config.OPENAI_API_KEY or not items:
        return [_fallback(item) for item in items]

    ctx_text = _build_context_text(context)
    items_json = json.dumps(
        [{"index": i + 1, "type": TYPE_LABELS.get(it.get("type", "chat"), "INSIGHT"),
          "label": it.get("label", ""), "content": it.get("content", "")}
         for i, it in enumerate(items)],
        indent=2,
    )

    try:
        resp = get_client().responses.parse(
            model=ELABORATION_MODEL,
            instructions=ELABORATION_PROMPT,
            input=f"Market context:\n{ctx_text}\n\nItems:\n{items_json}",
            text_format=ElaborationList,
        )
        if resp.output_parsed is None:
            raise ValueError("no structured output")
        elab_map = {e.index: e for e in resp.output_parsed.items}

        result = []
        for i, item in enumerate(items):
            e = elab_map.get(i + 1)
            result.append({**item,
                "heading":      e.heading if e else item.get("label", "Insight"),
                "elaboration":  e.elaboration if e else item.get("content", ""),
                "action_steps": list(e.action_steps) if e else [],
            })
        return result

    except Exception as exc:
        logger.warning("Report elaboration failed: %s", exc)
        return [_fallback(item) for item in items]


def _fallback(item: dict) -> dict:
    return {**item,
        "heading":      item.get("label", "Insight"),
        "elaboration":  item.get("content", ""),
        "action_steps": [],
    }


def _build_context_text(ctx: dict) -> str:
    lines = []
    t = ctx.get("totals") or {}
    if t:
        lines.append(
            f"Active jobs: {t.get('total_active','?')} | "
            f"Stale 30+: {t.get('stale_30','?')} | "
            f"Urgent ≤14d: {t.get('urgent_14d','?')}"
        )
    if ctx.get("headline"):
        lines.append(f"Headline: {ctx['headline']}")
    recs = ctx.get("recommendations") or []
    if recs:
        lines.append("Recommendations: " + " / ".join(recs[:5]))
    return "\n".join(lines) or "No context available."


# ── PDF builder ───────────────────────────────────────────────────────────────

def generate_pdf(elaborated: list[dict], context: dict, charts: list[dict] | None = None) -> bytes:
    """Build and return the report PDF as bytes."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN,  bottomMargin=MARGIN,
        title="Analytics Session Report",
    )

    # ── Styles
    def sty(name, **kw):
        return ParagraphStyle(name, **{"fontName": "Helvetica", "textColor": DARK, **kw})

    s_title    = sty("title",    fontName="Helvetica-Bold", fontSize=22, textColor=NAVY,
                     spaceBefore=0, spaceAfter=6, leading=28)
    s_subtitle = sty("sub",      fontSize=13, textColor=GREY, spaceAfter=2, leading=18)
    s_date     = sty("date",     fontSize=10, textColor=GREY, spaceAfter=0)
    s_hl       = sty("hl",       fontName="Helvetica-Oblique", fontSize=11, textColor=GREY,
                     leftIndent=8, spaceBefore=8, spaceAfter=4)
    s_stat_num = sty("statnum",  fontName="Helvetica-Bold", fontSize=18, textColor=NAVY, alignment=TA_CENTER)
    s_stat_lbl = sty("statlbl",  fontSize=8,  textColor=GREY, alignment=TA_CENTER)
    s_toc_sec  = sty("tocsec",   fontName="Helvetica-Bold", fontSize=10, textColor=NAVY,
                     spaceBefore=4, spaceAfter=2)
    s_toc_item = sty("tocitem",  fontSize=9, textColor=GREY, leftIndent=12, spaceAfter=1)
    s_sec_num  = sty("secnum",   fontName="Helvetica-Bold", fontSize=9,  textColor=WHITE,
                     alignment=TA_CENTER)
    s_sec_name = sty("secname",  fontName="Helvetica-Bold", fontSize=13, textColor=WHITE,
                     spaceAfter=0)
    s_heading  = sty("heading",  fontName="Helvetica-Bold", fontSize=13, textColor=NAVY,
                     spaceBefore=6, spaceAfter=8)
    s_badge    = sty("badge",    fontName="Helvetica-Bold", fontSize=8,  textColor=WHITE)
    s_orig_lbl = sty("origlbl", fontName="Helvetica-Bold", fontSize=8,  textColor=GREY,
                     spaceBefore=4, spaceAfter=3)
    s_orig     = sty("orig",    fontName="Helvetica-Oblique", fontSize=10, textColor=colors.HexColor("#444"),
                     leading=15, spaceAfter=0)
    s_body     = sty("body",    fontSize=10.5, leading=16, spaceAfter=6)
    s_act_head = sty("acthead", fontName="Helvetica-Bold", fontSize=10, textColor=NAVY,
                     spaceBefore=8, spaceAfter=4)
    s_action   = sty("action",  fontSize=10, leading=15, leftIndent=10, spaceAfter=3)
    s_footer   = sty("footer",  fontSize=8,  textColor=GREY, alignment=TA_CENTER)

    story = []
    today = date.today().strftime("%B %d, %Y")
    totals = context.get("totals") or {}

    # ── Group items by section type (preserving insertion order within each group)
    grouped: dict[str, list[dict]] = {k: [] for k in SECTION_ORDER}
    for item in elaborated:
        itype = item.get("type", "chat")
        if itype not in grouped:
            grouped.setdefault(itype, [])
        grouped[itype].append(item)
    # Only keep sections that have items, in defined order
    active_sections = [(t, grouped[t]) for t in SECTION_ORDER if grouped.get(t)]

    # ── Cover block
    story += [
        Spacer(1, 0.5 * cm),
        Paragraph("Jobs Intelligence Austria", s_title),
        Paragraph("Analytics Session Report", s_subtitle),
        Paragraph(f"Generated {today}", s_date),
        Spacer(1, 0.6 * cm),
    ]

    # Stats row
    active  = str(totals.get("total_active", "—"))
    stale30 = str(totals.get("stale_30", "—"))
    urgent  = str(totals.get("urgent_14d", "—"))
    n       = str(len(elaborated))
    cw = COL_W / 4

    stats = Table(
        [[Paragraph(v, s_stat_num) for v in [active, stale30, urgent, n]],
         [Paragraph(l, s_stat_lbl) for l in ["Active jobs", "Stale 30+ days", "Urgent ≤14 days", "Saved insights"]]],
        colWidths=[cw] * 4,
    )
    stats.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), LIGHT),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("GRID",          (0, 0), (-1, -1), 0.5, BORDER),
    ]))
    story.append(stats)

    if context.get("headline"):
        story.append(Paragraph(f'"{context["headline"]}"', s_hl))

    story += [
        Spacer(1, 0.5 * cm),
        HRFlowable(width="100%", thickness=1, color=BORDER, spaceAfter=0.4 * cm),
    ]

    # ── Table of Contents
    story.append(Paragraph("Contents", s_toc_sec))
    story.append(Spacer(1, 0.1 * cm))
    for sec_num, (itype, items) in enumerate(active_sections, 1):
        sec_name = SECTION_NAMES.get(itype, itype.title())
        story.append(Paragraph(
            f"Section {sec_num} — {sec_name}  ({len(items)} {'item' if len(items)==1 else 'items'})",
            s_toc_item,
        ))

    story += [
        Spacer(1, 0.4 * cm),
        HRFlowable(width="100%", thickness=1, color=BORDER, spaceAfter=0.6 * cm),
    ]

    # ── Sections
    for sec_num, (itype, items) in enumerate(active_sections, 1):
        sec_color  = colors.HexColor(TYPE_COLORS.get(itype, "#6b7280"))
        sec_name   = SECTION_NAMES.get(itype, itype.title())

        # Section header — full-width navy bar
        num_col_w = 52
        sec_header = Table(
            [[Paragraph(f"SECTION {sec_num}", s_sec_num),
              Paragraph(sec_name.upper(), s_sec_name)]],
            colWidths=[num_col_w, COL_W - num_col_w],
        )
        sec_header.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (0, -1), sec_color),
            ("BACKGROUND",    (1, 0), (1, -1), NAVY),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING",   (0, 0), (0, -1), 8),
            ("LEFTPADDING",   (1, 0), (1, -1), 14),
            ("RIGHTPADDING",  (1, 0), (1, -1), 8),
        ]))
        story += [sec_header, Spacer(1, 0.35 * cm)]

        # Items within this section
        for j, item in enumerate(items):
            badge_text = TYPE_LABELS.get(itype, "INSIGHT")

            # Badge + heading row
            badge_col_w = max(80, len(badge_text) * 6.5 + 16)
            badge_row = Table(
                [[Paragraph(f"  {badge_text}  ", s_badge),
                  Paragraph(item.get("heading", ""), s_heading)]],
                colWidths=[badge_col_w, COL_W - badge_col_w],
            )
            badge_row.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (0, 0), sec_color),
                ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING",    (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING",   (0, 0), (0, 0), 8),
                ("LEFTPADDING",   (1, 0), (1, 0), 12),
                ("RIGHTPADDING",  (1, 0), (1, 0), 4),
            ]))
            story.append(badge_row)

            # Original finding box
            if item.get("content"):
                story.append(Paragraph("ORIGINAL FINDING", s_orig_lbl))
                orig_box = Table(
                    [["", Paragraph(item["content"], s_orig)]],
                    colWidths=[5, COL_W - 5],
                )
                orig_box.setStyle(TableStyle([
                    ("BACKGROUND",    (0, 0), (0, -1), sec_color),
                    ("BACKGROUND",    (1, 0), (1, -1), LIGHT),
                    ("LEFTPADDING",   (0, 0), (0, -1), 0),
                    ("RIGHTPADDING",  (0, 0), (0, -1), 0),
                    ("LEFTPADDING",   (1, 0), (1, -1), 10),
                    ("RIGHTPADDING",  (1, 0), (1, -1), 10),
                    ("TOPPADDING",    (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]))
                story.append(orig_box)
                story.append(Spacer(1, 0.25 * cm))

            # Elaboration paragraphs
            for para in (item.get("elaboration") or "").split("\n\n"):
                para = para.strip()
                if para:
                    story.append(Paragraph(para, s_body))

            # Action steps
            steps = item.get("action_steps") or []
            if steps:
                story.append(Paragraph("Action Steps", s_act_head))
                for step in steps:
                    story.append(Paragraph(f"→  {step}", s_action))

            # Divider between items within a section
            if j < len(items) - 1:
                story += [Spacer(1, 0.5 * cm),
                          HRFlowable(width="100%", thickness=0.5, color=DIVIDER, spaceAfter=0.5 * cm)]

        # Space between sections (no page break — keeps it compact)
        story += [Spacer(1, 0.7 * cm),
                  HRFlowable(width="100%", thickness=1, color=BORDER, spaceAfter=0.7 * cm)]

    # ── Charts appendix (only when charts were captured)
    valid_charts = [c for c in (charts or []) if c.get("data_url", "").startswith("data:image/png;base64,")]
    if valid_charts:
        # Section header for charts
        chart_sec = Table(
            [[Paragraph("APPENDIX", s_sec_num), Paragraph("MARKET CHARTS", s_sec_name)]],
            colWidths=[52, COL_W - 52],
        )
        chart_sec.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (0, -1), colors.HexColor("#6b7280")),
            ("BACKGROUND",    (1, 0), (1, -1), NAVY),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING",   (0, 0), (0, -1), 8),
            ("LEFTPADDING",   (1, 0), (1, -1), 14),
            ("RIGHTPADDING",  (1, 0), (1, -1), 8),
        ]))
        story += [chart_sec, Spacer(1, 0.4 * cm)]

        s_chart_title = sty("charttitle", fontName="Helvetica-Bold", fontSize=10, textColor=NAVY,
                            spaceBefore=14, spaceAfter=6)

        for chart in valid_charts:
            try:
                raw = base64.b64decode(chart["data_url"].split(",", 1)[1])
                img_buf = io.BytesIO(raw)
                # Scale to fit page width while preserving aspect ratio
                img = Image(img_buf, width=COL_W, height=COL_W * 0.38)
                img.hAlign = "LEFT"
                story.append(Paragraph(chart.get("title", "Chart"), s_chart_title))
                story.append(img)
                story.append(Spacer(1, 0.3 * cm))
            except Exception as exc:
                logger.warning("Could not embed chart '%s': %s", chart.get("title"), exc)

        story += [Spacer(1, 0.4 * cm),
                  HRFlowable(width="100%", thickness=1, color=BORDER, spaceAfter=0.4 * cm)]

    # ── Footer
    story += [
        Spacer(1, 0.5 * cm),
        HRFlowable(width="100%", thickness=0.5, color=DIVIDER),
        Spacer(1, 0.2 * cm),
        Paragraph(f"Jobs Intelligence Austria  ·  Analytics Session Report  ·  {today}", s_footer),
    ]

    doc.build(story)
    return buf.getvalue()
