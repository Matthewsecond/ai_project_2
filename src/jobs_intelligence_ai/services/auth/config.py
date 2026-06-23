"""
config.py — settings for the `auth` service (flat constants, per rework §5).

The module's knobs: which schema the `users` table lives in (sourced from the global
environment config — login is shared across both country markets, so it's NOT split by
country) and the default accounts seeded when the table is empty.
"""
from jobs_intelligence_ai import config

# Schema holding the shared `users` table (global/environment identity).
APP_SCHEMA = config.APP_SCHEMA

# Seed users — created only when the users table is empty.
#   (username,    password,   display_name,    role)
SEED_USERS = [
    ("admin",      "admin",    "Administrator", "admin"),
    ("Monika2",    "m235",     "Monika",        "hr"),
    ("hr_manager", "jobs2024", "HR Manager",    "hr"),
]
