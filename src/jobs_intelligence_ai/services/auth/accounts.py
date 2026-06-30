"""
accounts.py — MySQL-backed authentication for Jobs Intelligence AI.

Users live in the Jobs_Intelligence_AI.app_user table (config.APP_SCHEMA) and each
belongs to an account_company (the tenant firm). Login is shared across both markets —
the same recruiters use the Austrian and Slovak apps — so users are NOT split by country
(unlike the saved_* pipeline tables, which carry a `country` column). Passwords are hashed
with werkzeug's pbkdf2.

Public API (unchanged names):
    init_db()                       — ensure tables exist + seed default company/accounts
    verify_login(username, pw)      — dict | None  (incl. account_company_id, role, visibility)
    list_users()                    — list[dict] (no hashes)
    create_user(username, pw, ...)  — add a user (admin UI / scripts)
"""
import logging

from sqlalchemy import text
from werkzeug.security import generate_password_hash, check_password_hash

from jobs_intelligence_ai.infra.database import get_engine
from .config import APP_SCHEMA as _DB, SEED_USERS as _SEED_USERS, DEFAULT_COMPANY as _DEFAULT_COMPANY

logger = logging.getLogger(__name__)


def init_db() -> None:
    """Ensure account_company + app_user exist and seed a default company/users if empty."""
    with get_engine().begin() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {_DB}.account_company (
                id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                name        VARCHAR(255)    NOT NULL,
                created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {_DB}.app_user (
                id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                account_company_id BIGINT UNSIGNED NOT NULL,
                username           VARCHAR(128)    NOT NULL,
                password_hash      VARCHAR(255)    NOT NULL,
                display_name       VARCHAR(255)    NOT NULL DEFAULT '',
                email              VARCHAR(255)    NULL,
                role               ENUM('admin','member') NOT NULL DEFAULT 'member',
                visibility         ENUM('own','all')      NOT NULL DEFAULT 'all',
                created_at         DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                UNIQUE KEY uq_user_username (username),
                KEY ix_user_company (account_company_id),
                CONSTRAINT fk_user_company FOREIGN KEY (account_company_id)
                    REFERENCES {_DB}.account_company (id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """))
        n = conn.execute(text(f"SELECT COUNT(*) FROM {_DB}.app_user")).scalar() or 0
        if n == 0:
            company_id = _ensure_default_company(conn)
            for username, password, display_name, role in _SEED_USERS:
                conn.execute(text(
                    f"INSERT INTO {_DB}.app_user "
                    f"(account_company_id, username, password_hash, display_name, role) "
                    f"VALUES (:c, :u, :p, :d, :r)"),
                    {"c": company_id, "u": username, "p": generate_password_hash(password),
                     "d": display_name, "r": role})
            logger.info("Seeded %d default users into %s.app_user", len(_SEED_USERS), _DB)


def _ensure_default_company(conn) -> int:
    """Return the id of the first account_company, creating the default one if none exist."""
    cid = conn.execute(text(
        f"SELECT id FROM {_DB}.account_company ORDER BY id LIMIT 1")).scalar()
    if cid is None:
        res = conn.execute(text(
            f"INSERT INTO {_DB}.account_company (name) VALUES (:n)"),
            {"n": _DEFAULT_COMPANY})
        cid = int(res.lastrowid)
    return int(cid)


def verify_login(username: str, password: str) -> dict | None:
    """Verify credentials. Returns the user dict (with account_company_id, role,
    visibility) or None."""
    with get_engine().connect() as conn:
        row = conn.execute(text(
            f"SELECT id, account_company_id, username, password_hash, display_name, "
            f"role, visibility FROM {_DB}.app_user WHERE username = :u LIMIT 1"),
            {"u": username}).mappings().first()
    if row and check_password_hash(row["password_hash"], password):
        return {"id": int(row["id"]),
                "account_company_id": int(row["account_company_id"]),
                "username": row["username"],
                "display_name": row["display_name"],
                "role": row["role"],
                "visibility": row["visibility"]}
    return None


def list_users() -> list[dict]:
    """Return all users (without password hashes) — for the admin UI."""
    with get_engine().connect() as conn:
        rows = conn.execute(text(
            f"SELECT id, account_company_id, username, display_name, role, visibility, "
            f"created_at FROM {_DB}.app_user ORDER BY id")).mappings().all()
    return [{"id": int(r["id"]), "account_company_id": int(r["account_company_id"]),
             "username": r["username"], "display_name": r["display_name"],
             "role": r["role"], "visibility": r["visibility"],
             "created_at": str(r["created_at"])} for r in rows]


def create_user(username: str, password: str, display_name: str = "",
                role: str = "member", account_company_id: int | None = None,
                visibility: str = "all") -> int | None:
    """Create a user. Returns the new id, or None if the username already exists.

    If account_company_id is not given, the user joins the first (default) company.
    """
    username = (username or "").strip()
    if not username or not password:
        raise ValueError("username and password required")
    with get_engine().begin() as conn:
        exists = conn.execute(text(
            f"SELECT 1 FROM {_DB}.app_user WHERE username = :u LIMIT 1"),
            {"u": username}).first()
        if exists:
            return None
        if account_company_id is None:
            account_company_id = _ensure_default_company(conn)
        res = conn.execute(text(
            f"INSERT INTO {_DB}.app_user "
            f"(account_company_id, username, password_hash, display_name, role, visibility) "
            f"VALUES (:c, :u, :p, :d, :r, :v)"),
            {"c": int(account_company_id), "u": username,
             "p": generate_password_hash(password),
             "d": display_name or username, "r": role, "v": visibility})
        return int(res.lastrowid)
