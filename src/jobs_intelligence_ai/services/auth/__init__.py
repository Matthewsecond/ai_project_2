"""
auth — MySQL-backed authentication for the app (shared across both country markets).

Owns the `users` table: create/seed it, verify logins, and manage accounts. DB only — no
LLM. Public API — import from the package:

    from jobs_intelligence_ai.services.auth import init_db, verify_login, list_users, create_user
"""
from .accounts import init_db, verify_login, list_users, create_user

__all__ = ["init_db", "verify_login", "list_users", "create_user"]
