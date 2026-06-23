# services/auth/

MySQL-backed authentication for the app. DB only — no LLM. Login is shared across both
country markets (the same recruiters use the AT and SK apps), so the `users` table is NOT
split by country. Packaged in rework Stage 2.3 #9 from the loose `services/auth.py`.

## Layout
```
services/auth/
├── __init__.py    # public API
├── config.py      # APP_SCHEMA (shared users schema) + SEED_USERS (default accounts)
└── accounts.py    # init_db / verify_login / list_users / create_user (SQLAlchemy)
```

## Public API
```python
from jobs_intelligence_ai.services.auth import init_db, verify_login, list_users, create_user
```
Consumer: `frontend/app.py` (`init_db` at startup, `verify_login` on the login route). The import
path is unchanged from the pre-package module — the package `__init__` exports the same names.

## Tests
`tests/jobs_intelligence_ai/services/auth/unit_tests/test_1_verify_login.py` (3, offline):
pins the password check via a tiny inline fake engine — correct password → user dict (no
hash), wrong password / unknown user → None. `init_db` / `create_user` / `list_users` are
covered by boot + the login flow (no live-DB unit harness, matching the `stats` precedent).
