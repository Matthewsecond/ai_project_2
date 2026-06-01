"""
app.py — Jobs Intelligence AI: application entry point.

Registers all tab blueprints and handles auth, login/logout, and the main page.
Tab-specific logic lives in tabs/<tab_name>.py.

Run:
    python app.py
Then open: http://localhost:5000
"""
from datetime import date
from flask import Flask, jsonify, render_template, request, redirect, url_for, session
import config
from tabs import register_blueprints

app = Flask(__name__)
app.json.sort_keys = False
app.secret_key = "jia-demo-secret-2024-xK9pLm"   # change in production

# ── Auth ──────────────────────────────────────────────────────────────────────
from helpers.auth import init_db, verify_login
init_db()

_PUBLIC_ENDPOINTS = {"login", "static"}


@app.before_request
def require_login():
    if request.endpoint in _PUBLIC_ENDPOINTS:
        return
    if "user_id" not in session:
        if request.is_json or request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        return redirect(url_for("login"))


# ── Login / logout ────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        user     = verify_login(username, password)
        if user:
            session.clear()
            session["user_id"]      = user["id"]
            session["username"]     = user["username"]
            session["display_name"] = user["display_name"]
            session["role"]         = user["role"]
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


# ── Main page ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template(
        "index.html",
        current_user=session.get("display_name") or session.get("username", ""),
    )


# ── Tab blueprints ────────────────────────────────────────────────────────────

register_blueprints(app)


# ── Debug / test endpoints ────────────────────────────────────────────────────

@app.route("/api/test/match")
def api_test_match():
    from test.fixtures import SAMPLE_JOBS
    return jsonify({"ok": True, "count": len(SAMPLE_JOBS), "top_n": len(SAMPLE_JOBS), "jobs": SAMPLE_JOBS})


@app.route("/test/job-detail")
@app.route("/test/job-detail/<int:n>")
def test_job_detail(n: int = 0):
    from test.fixtures import SAMPLE_JOBS
    from core.job_detail import JobDetail
    job      = JobDetail.from_dict(SAMPLE_JOBS[n % len(SAMPLE_JOBS)])
    all_jobs = [JobDetail.from_dict(j).to_dict() for j in SAMPLE_JOBS]
    return render_template("job_detail_test.html", job=job.to_dict(), all_jobs=all_jobs, n=n, total=len(SAMPLE_JOBS))


@app.route("/debug/schema")
def debug_schema():
    from core.database import describe_view
    try:
        return jsonify({"ok": True, "columns": describe_view()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n  Jobs Intelligence AI")
    print(f"  http://localhost:{config.FLASK_PORT}")
    print(f"  Schema debug: http://localhost:{config.FLASK_PORT}/debug/schema\n")
    app.run(host="0.0.0.0", port=config.FLASK_PORT, debug=config.FLASK_DEBUG)
