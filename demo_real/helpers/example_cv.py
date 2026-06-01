"""
helpers/example_cv.py — generate a sample candidate CV PDF for demonstration.
"""
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

PAGE_W, PAGE_H = A4
MARGIN = 2.2 * cm
COL_W  = PAGE_W - 2 * MARGIN

NAVY   = colors.HexColor("#1a3864")
GREY   = colors.HexColor("#6b7280")
DARK   = colors.HexColor("#1a1a18")
DIVIDER= colors.HexColor("#e5e7eb")


def generate_example_cv_pdf() -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN,  bottomMargin=MARGIN,
        title="Anna Bauer — CV",
    )

    def sty(name, **kw):
        params = dict(fontName="Helvetica", textColor=DARK)
        params.update(kw)
        return ParagraphStyle(name, **params)

    s_name   = sty("name",  fontName="Helvetica-Bold", fontSize=22, textColor=NAVY,
                   spaceAfter=3, leading=26)
    s_title  = sty("title", fontSize=13, textColor=GREY, spaceAfter=2)
    s_contact= sty("cont",  fontSize=10, textColor=GREY, spaceAfter=0)
    s_section= sty("sec",   fontName="Helvetica-Bold", fontSize=10, textColor=NAVY,
                   spaceBefore=14, spaceAfter=4, textTransform="uppercase")
    s_body   = sty("body",  fontSize=10, leading=15, spaceAfter=4)
    s_jobt   = sty("jobt",  fontName="Helvetica-Bold", fontSize=10, spaceAfter=1)
    s_jobco  = sty("jobco", fontSize=10, textColor=GREY, spaceAfter=4)
    s_bullet = sty("bul",   fontSize=10, leading=15, leftIndent=10, spaceAfter=2)
    s_inline = sty("inline",fontSize=10, leading=15, spaceAfter=4)

    story = [
        Paragraph("Anna Bauer", s_name),
        Paragraph("Logistics &amp; Warehouse Supervisor", s_title),
        Paragraph("Vienna, Austria  ·  anna.bauer@example.at  ·  +43 699 123 456 78", s_contact),
        Spacer(1, 0.3 * cm),
        HRFlowable(width="100%", thickness=2, color=NAVY, spaceAfter=0.4 * cm),
    ]

    def section(title):
        story.append(Paragraph(title, s_section))

    def hr():
        story.append(HRFlowable(width="100%", thickness=0.5, color=DIVIDER, spaceAfter=0.1 * cm))

    # ── Profile
    section("Profile")
    story.append(Paragraph(
        "Logistics and warehouse professional with 8 years of experience in high-volume distribution "
        "centres across Vienna and Lower Austria. Proven track record in team leadership, inventory "
        "management, and process optimisation. Certified forklift operator (Staplerführerschein). "
        "SAP WM certified user. Available immediately for permanent full-time opportunities.",
        s_body,
    ))
    hr()

    # ── Work experience
    section("Work Experience")
    jobs = [
        ("2019 – present", "Senior Warehouse Supervisor", "MegaLogistics GmbH, Wien",
         ["Led a team of 12 warehouse associates across two shifts.",
          "Introduced SAP WM module — reduced stock discrepancies by 23%.",
          "Managed incoming/outgoing freight and carrier coordination.",
          "KPI reporting to senior management (fill rate, OTIF, pick accuracy)."]),
        ("2016 – 2019", "Warehouse Coordinator", "AustroPack AG, Niederösterreich",
         ["Coordinated daily pick &amp; pack operations (2,000+ orders/day).",
          "Trained and onboarded 8 new team members.",
          "Maintained FIFO/FEFO inventory rotation procedures."]),
        ("2015 – 2016", "Warehouse Associate", "LogiStart GmbH, Wien",
         ["General warehouse duties and forklift operation.",
          "Supported stocktakes and cycle counting."]),
    ]
    YR_W = 3.0 * cm
    for years, jobt, company, bullets in jobs:
        row = Table(
            [[Paragraph(years, s_contact), Paragraph(jobt, s_jobt)]],
            colWidths=[YR_W, COL_W - YR_W],
        )
        row.setStyle(TableStyle([
            ("VALIGN",      (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",(0, 0), (-1, -1), 0),
            ("TOPPADDING",  (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING",(0,0), (-1, -1), 0),
        ]))
        story.append(row)
        story.append(Paragraph(company, s_jobco))
        for b in bullets:
            story.append(Paragraph(f"·  {b}", s_bullet))
        story.append(Spacer(1, 0.1 * cm))
    hr()

    # ── Education
    section("Education")
    edu = Table(
        [[Paragraph("2013 – 2015", s_contact),
          Paragraph("HLA für Touristik und Wirtschaft, Wien — Commerce &amp; Business Diploma", s_body)]],
        colWidths=[YR_W, COL_W - YR_W],
    )
    edu.setStyle(TableStyle([
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING",  (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",(0,0), (-1, -1), 0),
    ]))
    story.append(edu)
    hr()

    # ── Certifications
    section("Certifications")
    for cert in [
        "Staplerführerschein (Forklift licence) — valid until 2027",
        "SAP WM Certified User (2020)",
    ]:
        story.append(Paragraph(f"·  {cert}", s_bullet))
    hr()

    # ── Skills
    section("Skills")
    story.append(Paragraph(
        "SAP Warehouse Management  ·  Forklift Operation  ·  Inventory Control  ·  "
        "Team Leadership  ·  KPI Reporting  ·  MS Excel  ·  Lean Logistics  ·  FIFO/FEFO Principles",
        s_inline,
    ))
    hr()

    # ── Languages
    section("Languages")
    story.append(Paragraph("German: Native  ·  English: B2 (Upper Intermediate)", s_inline))
    hr()

    # ── Expectations
    section("Availability & Expectations")
    story.append(Paragraph(
        "Salary expectation: €2,800–3,400 gross/month  ·  Available: immediately  ·  "
        "Work preference: Full-time permanent, Vienna or Niederösterreich",
        s_inline,
    ))

    doc.build(story)
    return buf.getvalue()


def generate_example_cv_pdf_2() -> bytes:
    """Generate a sample CV PDF for Max Weber, Software Developer."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN,  bottomMargin=MARGIN,
        title="Max Weber — CV",
    )

    def sty(name, **kw):
        params = dict(fontName="Helvetica", textColor=DARK)
        params.update(kw)
        return ParagraphStyle(name, **params)

    s_name   = sty("name2",  fontName="Helvetica-Bold", fontSize=22, textColor=NAVY, spaceAfter=3, leading=26)
    s_title  = sty("title2", fontSize=13, textColor=GREY, spaceAfter=2)
    s_contact= sty("cont2",  fontSize=10, textColor=GREY, spaceAfter=0)
    s_section= sty("sec2",   fontName="Helvetica-Bold", fontSize=10, textColor=NAVY, spaceBefore=14, spaceAfter=4)
    s_body   = sty("body2",  fontSize=10, leading=15, spaceAfter=4)
    s_jobt   = sty("jobt2",  fontName="Helvetica-Bold", fontSize=10, spaceAfter=1)
    s_jobco  = sty("jobco2", fontSize=10, textColor=GREY, spaceAfter=4)
    s_bullet = sty("bul2",   fontSize=10, leading=15, leftIndent=10, spaceAfter=2)
    s_inline = sty("inl2",   fontSize=10, leading=15, spaceAfter=4)

    story = [
        Paragraph("Max Weber", s_name),
        Paragraph("Backend &amp; Full-Stack Developer", s_title),
        Paragraph("Vienna, Austria  ·  max.weber@example.at  ·  +43 676 987 654 32", s_contact),
        Spacer(1, 0.3 * cm),
        HRFlowable(width="100%", thickness=2, color=NAVY, spaceAfter=0.4 * cm),
    ]

    def section(title):
        story.append(Paragraph(title.upper(), s_section))

    def hr():
        story.append(HRFlowable(width="100%", thickness=0.5, color=DIVIDER, spaceAfter=0.1 * cm))

    section("Profile")
    story.append(Paragraph(
        "Software developer with 5 years of experience in backend and full-stack development. "
        "Specialised in Python/FastAPI REST APIs and React frontends, with hands-on experience "
        "deploying services via Docker and CI/CD pipelines. BSc Computer Science from FH Technikum Wien. "
        "Available in Vienna; open to hybrid or on-site roles.",
        s_body,
    ))
    hr()

    section("Work Experience")
    YR_W = 3.0 * cm
    jobs = [
        ("2022 – present", "Backend Developer", "TechSolutions GmbH, Vienna",
         ["Designed and maintained REST APIs using Python and FastAPI.",
          "Managed PostgreSQL schema migrations and query optimisation.",
          "Containerised services with Docker; maintained CI/CD pipelines (GitHub Actions).",
          "Participated in agile sprints and conducted regular code reviews."]),
        ("2020 – 2022", "Junior Developer", "WebFactory GmbH, Vienna",
         ["Built React/TypeScript frontends consuming REST and GraphQL APIs.",
          "Developed Node.js microservices for internal tooling.",
          "Contributed to sprint planning and technical documentation."]),
        ("2019 – 2020", "IT Intern", "Startup Hub Vienna",
         ["Automated reporting workflows with Python scripts.",
          "Built internal dashboards using Flask and SQLite."]),
    ]
    for years, jobt, company, bullets in jobs:
        row = Table(
            [[Paragraph(years, s_contact), Paragraph(jobt, s_jobt)]],
            colWidths=[YR_W, COL_W - YR_W],
        )
        row.setStyle(TableStyle([
            ("VALIGN",      (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",(0, 0), (-1, -1), 0),
            ("TOPPADDING",  (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING",(0,0), (-1, -1), 0),
        ]))
        story.append(row)
        story.append(Paragraph(company, s_jobco))
        for b in bullets:
            story.append(Paragraph(f"·  {b}", s_bullet))
        story.append(Spacer(1, 0.1 * cm))
    hr()

    section("Education")
    edu = Table(
        [[Paragraph("2016 – 2019", s_contact),
          Paragraph("FH Technikum Wien — BSc Computer Science", s_body)]],
        colWidths=[YR_W, COL_W - YR_W],
    )
    edu.setStyle(TableStyle([
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING",  (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",(0,0), (-1, -1), 0),
    ]))
    story.append(edu)
    hr()

    section("Skills")
    story.append(Paragraph(
        "Python  ·  FastAPI  ·  JavaScript / TypeScript  ·  React  ·  Node.js  ·  "
        "PostgreSQL  ·  Docker  ·  Git  ·  REST APIs  ·  Linux  ·  CI/CD (GitHub Actions)",
        s_inline,
    ))
    hr()

    section("Languages")
    story.append(Paragraph("German: Native  ·  English: C1 (Advanced)", s_inline))
    hr()

    section("Availability & Expectations")
    story.append(Paragraph(
        "Salary expectation: €3,500–4,500 gross/month  ·  Notice period: 3 months  ·  "
        "Work preference: Full-time permanent, Vienna (hybrid/on-site)",
        s_inline,
    ))

    doc.build(story)
    return buf.getvalue()
