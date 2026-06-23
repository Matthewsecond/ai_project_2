"""
accounts.py — MySQL-backed authentication for Jobs Intelligence AI.

Users live in the Jobs_Intelligence_AI.users table (config.APP_SCHEMA, migrated
from the old SQLite users.db). Login is shared across both markets — the same
recruiters use the Austrian and Slovak apps — so `users` is intentionally NOT
split by country (unlike the candidate pipeline tables, which are prefixed per
country in candidate/store.py). Passwords are hashed with werkzeug's pbkdf2.

Public API (unchanged):
    init_db()                       — ensure table exists + seed default accounts
    verify_login(username, pw)      — dict | None
    list_users()                    — list[dict] (no hashes)
    create_user(username, pw, ...)  — add a user (admin UI / scripts)
"""
import logging

from sqlalchemy import text
from werkzeug.security import generate_password_hash, check_password_hash

from jobs_intelligence_ai.infra.database import get_engine
from .config import APP_SCHEMA as _DB, SEED_USERS as _SEED_USERS

logger = logging.getLogger(__name__)


def init_db() -> None:
    """Ensure the users table exists and seed default accounts if it is empty."""
    with get_engine().begin() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {_DB}.users (
                id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                username       VARCHAR(128)    NOT NULL,
                password_hash  VARCHAR(255)    NOT NULL,
                display_name   VARCHAR(255)    NOT NULL DEFAULT '',
                role           VARCHAR(32)     NOT NULL DEFAULT 'hr',
                created_at     DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                UNIQUE KEY uq_users_username (username)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """))
        n = conn.execute(text(f"SELECT COUNT(*) FROM {_DB}.users")).scalar() or 0
        if n == 0:
            for username, password, display_name, role in _SEED_USERS:
                conn.execute(text(
                    f"INSERT INTO {_DB}.users (username, password_hash, display_name, role) "
                    f"VALUES (:u, :p, :d, :r)"),
                    {"u": username, "p": generate_password_hash(password),
                     "d": display_name, "r": role})
            logger.info("Seeded %d default users into %s.users", len(_SEED_USERS), _DB)


def verify_login(username: str, password: str) -> dict | None:
    """Verify credentials. Returns {id, username, display_name, role} or None."""
    with get_engine().connect() as conn:
        row = conn.execute(text(
            f"SELECT id, username, password_hash, display_name, role "
            f"FROM {_DB}.users WHERE username = :u LIMIT 1"),
            {"u": username}).mappings().first()
    if row and check_password_hash(row["password_hash"], password):
        return {"id": int(row["id"]), "username": row["username"],
                "display_name": row["display_name"], "role": row["role"]}
    return None


def list_users() -> list[dict]:
    """Return all users (without password hashes) — for the admin UI."""
    with get_engine().connect() as conn:
        rows = conn.execute(text(
            f"SELECT id, username, display_name, role, created_at "
            f"FROM {_DB}.users ORDER BY id")).mappings().all()
    return [{"id": int(r["id"]), "username": r["username"],
             "display_name": r["display_name"], "role": r["role"],
             "created_at": str(r["created_at"])} for r in rows]


def create_user(username: str, password: str, display_name: str = "",
                role: str = "hr") -> int | None:
    """Create a user. Returns the new id, or None if the username already exists."""
    username = (username or "").strip()
    if not username or not password:
        raise ValueError("username and password required")
    with get_engine().begin() as conn:
        exists = conn.execute(text(
            f"SELECT 1 FROM {_DB}.users WHERE username = :u LIMIT 1"),
            {"u": username}).first()
        if exists:
            return None
        res = conn.execute(text(
            f"INSERT INTO {_DB}.users (username, password_hash, display_name, role) "
            f"VALUES (:u, :p, :d, :r)"),
            {"u": username, "p": generate_password_hash(password),
             "d": display_name or username, "r": role})
        return int(res.lastrowid)
