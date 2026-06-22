"""
Test fixtures — pre-built job objects matching the _serialize_job() shape.
Used by the /api/test/match endpoint to test the modal without a live DB query.

occ_group values chosen to match the Austrian DB taxonomy so salary_stats
will return real market data (or at least show the "no data" state cleanly).
"""

SAMPLE_JOBS = [
    {
        "job_id":      "test-001",
        "title":       "Staplerfahrer / LagerarbeiterIn",
        "company":     "Logistik Austria GmbH",
        "state":       "Wien",
        "city":        "Wien, 22. Bezirk",
        "salary":      "2200",
        "occ_group":   "LagerarbeiterIn",
        "portal":      "ams",
        "posted":      "2026-05-01",
        "url":         "https://www.ams.at/",
        "lat":         48.2302,
        "lon":         16.4255,
        "score":       0.89,
        "score_pct":   "89%",
        "grade":       "A",
        "match_reason": "Forklift licence + warehouse experience match exactly",
        "skills":      "Staplerschein, Lagerlogistik, SAP WMS, Schichtarbeit, Wareneingang",
        "skills_en":   "Forklift licence, Warehouse logistics, SAP WMS, Shift work, Goods receipt",
        "description": (
            "We are looking for an experienced forklift operator for our modern logistics centre "
            "in Vienna's 22nd district.\n\n"
            "Your tasks:\n"
            "• Operating reach trucks and counterbalance forklifts\n"
            "• Goods receipt and dispatch management\n"
            "• Inventory management in SAP WMS\n"
            "• Collaboration in a team of 15\n\n"
            "Requirements:\n"
            "• Valid Staplerschein (forklift licence)\n"
            "• Minimum 2 years warehouse experience\n"
            "• German language skills B2\n"
            "• Reliability and willingness to work 2-shift rotation (06:00–14:00 / 14:00–22:00)\n\n"
            "We offer: €2,200 gross/month + shift allowance, meal vouchers, job ticket."
        ),
    },
    {
        "job_id":      "test-002",
        "title":       "Software Developer — Python / React",
        "company":     "Tech Innovations Wien GmbH",
        "state":       "Wien",
        "city":        "Wien, 3. Bezirk",
        "salary":      "4200",
        "occ_group":   "SoftwareentwicklerIn",
        "portal":      "karriere",
        "posted":      "2026-05-10",
        "url":         "https://www.karriere.at/",
        "lat":         48.1980,
        "lon":         16.3820,
        "score":       0.83,
        "score_pct":   "83%",
        "grade":       "A",
        "match_reason": "Python and React skills align with full-stack requirements",
        "skills":      "Python, React, FastAPI, Docker, PostgreSQL, REST API, Agile/Scrum",
        "skills_en":   "Python, React, FastAPI, Docker, PostgreSQL, REST API, Agile/Scrum",
        "description": (
            "Join our growing product team as a Full Stack Developer. You will work on a B2B SaaS "
            "platform used by 500+ companies across Europe.\n\n"
            "Tech stack: Python (FastAPI), React (TypeScript), PostgreSQL, Docker / Kubernetes, "
            "GitHub Actions CI/CD.\n\n"
            "Requirements:\n"
            "• 3+ years backend experience with Python\n"
            "• Strong SQL skills (query optimisation, indexing)\n"
            "• React or equivalent frontend experience\n"
            "• Good English (team language)\n\n"
            "Nice to have: AWS/GCP experience, event-driven architecture (Kafka/RabbitMQ).\n\n"
            "Salary: €4,200 gross/month, all-in. Flexible remote/office split (2 office days/week)."
        ),
    },
    {
        "job_id":      "test-003",
        "title":       "Köchin / Koch — Vollzeit",
        "company":     "Hotel Sacher Gruppe",
        "state":       "Wien",
        "city":        "Wien, 1. Bezirk",
        "salary":      "2100",
        "occ_group":   "KochIn",
        "portal":      "stepstone",
        "posted":      "2026-04-28",
        "url":         "https://www.stepstone.at/",
        "lat":         48.2040,
        "lon":         16.3700,
        "score":       0.72,
        "score_pct":   "72%",
        "grade":       "B",
        "match_reason": "Professional cooking experience and à la carte background relevant",
        "skills":      "Kochen, Menüplanung, HACCP, À la carte, Teamführung, Kalte Küche",
        "skills_en":   "Cooking, Menu planning, HACCP, À la carte service, Team leadership, Cold kitchen",
        "description": (
            "We are looking for a passionate chef to join our kitchen brigade.\n\n"
            "Responsibilities:\n"
            "• Preparation of high-quality dishes (à la carte + banqueting)\n"
            "• Assistance in seasonal menu planning\n"
            "• HACCP compliance and kitchen hygiene documentation\n"
            "• Mentoring kitchen apprentices\n\n"
            "Requirements:\n"
            "• Completed apprenticeship as cook\n"
            "• At least 3 years in professional gastronomy\n"
            "• Good German (B2)\n"
            "• Weekend and holiday availability\n\n"
            "We offer: €2,100 gross/month + service charge, staff meals, uniform."
        ),
    },
    {
        "job_id":      "test-004",
        "title":       "Pflegefachkraft / DGKP",
        "company":     "Wiener Gesundheitsverbund",
        "state":       "Wien",
        "city":        "Wien, 10. Bezirk",
        "salary":      "3100",
        "occ_group":   "KrankenpflegerIn",
        "portal":      "ams",
        "posted":      "2026-05-12",
        "url":         "https://www.ams.at/",
        "lat":         48.1750,
        "lon":         16.3740,
        "score":       0.66,
        "score_pct":   "66%",
        "grade":       "B",
        "match_reason": "Nursing qualification and inpatient care experience match posting",
        "skills":      "Krankenpflege, Patientenbetreuung, Wundversorgung, Medikamentengabe, Pflegedokumentation",
        "skills_en":   "Nursing care, Patient assessment, Wound care, Medication administration, Care documentation",
        "description": (
            "The Wiener Gesundheitsverbund is looking for a registered nurse (DGKP) for the "
            "internal medicine ward at KFJ Hospital.\n\n"
            "Your tasks:\n"
            "• Independent care of patients in accordance with the nursing process\n"
            "• Medication administration and wound care\n"
            "• Documentation in the Orbis patient information system\n"
            "• Coordination with medical and therapeutic teams\n\n"
            "Requirements:\n"
            "• Completed DGKP training with valid registration (Gesundheitsberuferegister)\n"
            "• Empathy, resilience, teamwork\n"
            "• German C1\n\n"
            "Salary: €3,100 gross/month (KV Wiener Krankenanstalten) + night/weekend allowances."
        ),
    },
    {
        "job_id":      "test-005",
        "title":       "Reinigungskraft (m/w/d) — Teilzeit",
        "company":     "CleanService Austria",
        "state":       "Niederösterreich",
        "city":        "Klosterneuburg",
        "salary":      "1300",
        "occ_group":   "RaumpflegerIn",
        "portal":      "ams",
        "posted":      "2026-05-15",
        "url":         "https://www.ams.at/",
        "lat":         48.3044,
        "lon":         16.3267,
        "score":       0.44,
        "score_pct":   "44%",
        "grade":       "C",
        "match_reason": "Cleaning experience present but candidate profile suggests higher role aspirations",
        "skills":      "Unterhaltsreinigung, Büroreinigung, Grundreinigung, Reinigungsmittel",
        "skills_en":   "Maintenance cleaning, Office cleaning, Deep cleaning, Cleaning agents",
        "description": (
            "Part-time cleaning role for office and commercial premises in Klosterneuburg.\n\n"
            "Hours: Monday–Friday, 06:00–10:00 (20 h/week).\n\n"
            "Requirements:\n"
            "• Experience in building or office cleaning preferred\n"
            "• Reliability and attention to detail\n"
            "• German A2 minimum\n"
            "• Driving licence category B an advantage (own vehicle or public transport)\n\n"
            "Pay: €1,300 gross/month (part-time 20 h). "
            "Immediate start available."
        ),
    },
]
