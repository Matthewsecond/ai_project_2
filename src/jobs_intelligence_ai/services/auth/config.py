"""
config.py — settings for the `auth` service (flat constants, per rework §5).

The module's knobs: which schema the `app_user` / `account_company` tables live in
(sourced from the global environment config — login is shared across both country
markets, so it's NOT split by country) and the default company + accounts seeded when
the user table is empty.
"""
from jobs_intelligence_ai import config

# Schema holding the shared `app_user` + `account_company` tables (global identity).
APP_SCHEMA = config.APP_SCHEMA

# Default tenant created when seeding a fresh DB (all seed users belong to it).
DEFAULT_COMPANY = "Acme Recruitment"

# Seed users — created only when the app_user table is empty.
#   (username,    password,   display_name,    role)   role in {admin, member}
SEED_USERS = [
    ("admin",      "admin",    "Administrator", "admin"),
    ("Monika2",    "m235",     "Monika",        "member"),
    ("hr_manager", "jobs2024", "HR Manager",    "member"),
]
