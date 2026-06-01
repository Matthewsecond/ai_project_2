"""
helpers/auth.py — Simple SQLite-backed authentication for Jobs Intelligence Austria.

Users are stored in users.db in the project root.
Passwords are hashed with werkzeug's pbkdf2 (ships with Flask).
"""
import os
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

# DB lives in the project root (one level up from this helpers/ directory)
_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "users.db")

# ── Seed users ────────────────────────────────────────────────────────────────
_SEED_USERS = [
    # (username,    password,  display_name,   role)
    ("admin",      "admin",   "Administrator", "admin"),
    ("Monika2",    "m235",    "Monika",        "hr"),
    ("hr_manager", "jobs2024","HR Manager",    "hr"),
]


def init_db() -> None:
    """Create the users table and seed default accounts if empty."""
    conn = sqlite3.connect(_DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            username     TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            role         TEXT NOT NULL DEFAULT 'hr'
        )
    """)
    conn.commit()

    # Only seed when the table is empty so we don't overwrite changed passwords
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        for username, password, display_name, role in _SEED_USERS:
            c.execute(
                "INSERT INTO users (username, password_hash, display_name, role) VALUES (?, ?, ?, ?)",
                (username, generate_password_hash(password), display_name, role),
            )
        conn.commit()
    conn.close()


def verify_login(username: str, password: str) -> dict | None:
    """
    Verify credentials.  Returns a user dict on success, None on failure.
    The dict contains: id, username, display_name, role  (no password hash).
    """
    conn = sqlite3.connect(_DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT id, username, password_hash, display_name, role FROM users WHERE username = ?",
        (username,),
    )
    row = c.fetchone()
    conn.close()

    if row and check_password_hash(row[2], password):
        return {"id": row[0], "username": row[1],
                "display_name": row[3], "role": row[4]}
    return None


def list_users() -> list[dict]:
    """Return all users (without password hashes) — for admin UI."""
    conn = sqlite3.connect(_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, username, display_name, role FROM users ORDER BY id")
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "username": r[1], "display_name": r[2], "role": r[3]}
            for r in rows]
