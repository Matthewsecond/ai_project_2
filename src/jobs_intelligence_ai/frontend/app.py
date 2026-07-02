"""
app.py — Jobs Intelligence AI: Flask application factory + entry point.

`create_app()` builds the app, registers every blueprint, and wires auth.
Blueprint logic lives in jobs_intelligence_ai/frontend/blueprints/<name>.py.

Run:
    python -m jobs_intelligence_ai                 # Austria (default)
    python -m jobs_intelligence_ai --country sk    # Slovakia
    python -m jobs_intelligence_ai --sk            # shorthand for --country sk
    jobs-intelligence-ai --sk                      # installed console script
Then open: http://localhost:5000
"""
import os
import sys
from datetime import date
from flask import Flask, jsonify, render_template, request, redirect, url_for, session


def _country_from_cli() -> str | None:
    """Read the country off the command line. Returns None if no flag was given.

    Supported: --country <code>, -c <code>, and the shortcuts --sk / --at.
    """
    argv = sys.argv[1:]
    for i, arg in enumerate(argv):
        if arg in ("--country", "-c") and i + 1 < len(argv):
            return argv[i + 1].lower()
        if arg == "--sk":
            return "sk"
        if arg == "--at":
            return "at"
    return None


def create_app() -> Flask:
    """Build and configure the Flask app.

    Imports `config` lazily (inside this function) so any COUNTRY override set in
    the environment *before* create_app() runs is honoured: config resolves the
    active profile at import time, and the blueprints below `import config` at
    module load, so everything must be imported after the env is set. See main().
    """
    from jobs_intelligence_ai import config
    from jobs_intelligence_ai.frontend import register_blueprints
    from jobs_intelligence_ai.services.auth import init_db, verify_login

    app = Flask(__name__)            # templates/ resolves to frontend/templates/ (package-relative)
    app.json.sort_keys = False
    app.secret_key = "jia-demo-secret-2024-xK9pLm"   # change in production

    @app.context_processor
    def _inject_country():
        """Make the active country's branding + feature flags available to every template."""
        return {
            "country_code":    config.COUNTRY,        # "at" / "sk" — drives JS example set
            "country_label":   config.COUNTRY_LABEL,
            "country_demonym": config.COUNTRY_DEMONYM,
            "has_guided":      config.HAS_GUIDED,
            "has_map":         config.HAS_MAP,
            "has_analytics":   config.HAS_ANALYTICS,
            "has_occ_filter":  config.HAS_OCC_FILTER,
        }

    # ── Auth ──────────────────────────────────────────────────────────────────
    init_db()

    # ── Demo reset ─────────────────────────────────────────────────────────────
    # Wipe the bundled example candidates on startup so each demo run starts clean
    # (their saved jobs cascade). Only the known demo names are removed — anything
    # saved under a different name persists across restarts. We match against the
    # union of both countries' demo names (the saved demo data isn't cleanly
    # partitioned by country), still scoped to the active country column. See
    # services/candidate/config.DEMO_CANDIDATE_NAMES.
    try:
        from jobs_intelligence_ai.services.candidate import store as _cand_store
        from jobs_intelligence_ai.services.candidate.config import DEMO_CANDIDATE_NAMES
        _demo_names = sorted({n for names in DEMO_CANDIDATE_NAMES.values() for n in names})
        _n = _cand_store.reset_demo_candidates(_demo_names)
        if _n:
            print(f"  Demo reset: cleared {_n} demo candidate(s)")
    except Exception as _e:
        print(f"  Demo reset skipped: {_e}")

    _PUBLIC_ENDPOINTS = {"login", "static"}

    @app.before_request
    def require_login():
        if request.endpoint in _PUBLIC_ENDPOINTS:
            return
        if "user_id" not in session:
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"ok": False, "error": "Unauthorized"}), 401
            return redirect(url_for("login"))

    # ── Login / logout ─────────────────────────────────────────────────────────
    @app.route("/login", methods=["GET", "POST"])
    def login():
        error = None
        if request.method == "POST":
            username = (request.form.get("username") or "").strip()
            password = request.form.get("password") or ""
            user     = verify_login(username, password)
            if user:
                session.clear()
                session["user_id"]            = user["id"]
                session["account_company_id"] = user["account_company_id"]
                session["username"]           = user["username"]
                session["display_name"]       = user["display_name"]
                session["role"]               = user["role"]
                session["visibility"]         = user["visibility"]
                return redirect(url_for("index"))
            error = "Incorrect username or password."
        return render_template(
            "login.html",
            error=error,
            prefill_user="admin",
            prefill_pass="admin",
            year=date.today().year,
        )

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    # ── Main page ──────────────────────────────────────────────────────────────
    @app.route("/")
    def index():
        return render_template(
            "index.html",
            current_user=session.get("display_name") or session.get("username", ""),
        )

    # ── Tab blueprints ─────────────────────────────────────────────────────────
    register_blueprints(app)

    # ── Debug endpoints ────────────────────────────────────────────────────────
    @app.route("/debug/schema")
    def debug_schema():
        from jobs_intelligence_ai.infra.database import describe_view
        try:
            return jsonify({"ok": True, "columns": describe_view()})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    return app


def main():
    """Console entry point: apply the CLI country flag, then build and run."""
    cli_country = _country_from_cli()
    if cli_country:
        os.environ["COUNTRY"] = cli_country

    from jobs_intelligence_ai import config
    app = create_app()
    print(f"\n  Jobs Intelligence AI — {config.COUNTRY_LABEL} ({config.COUNTRY})")
    print(f"  http://localhost:{config.FLASK_PORT}")
    print(f"  Schema debug: http://localhost:{config.FLASK_PORT}/debug/schema\n")
    app.run(host="0.0.0.0", port=config.FLASK_PORT, debug=config.FLASK_DEBUG)


if __name__ == "__main__":
    main()
