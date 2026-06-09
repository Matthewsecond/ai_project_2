"""
guided_chat.py — Live console tester for the "Build a candidate" guided builder.

An interactive REPL that talks to POST /api/guided/chat exactly like the
browser front-end does: it keeps a single shared `draft`, remembers the options
offered last turn (so "all" / "choose all" resolves), and sends the active AI
language. Each turn it prints the assistant's reply, its narrowing question, the
live data-grounded quick-pick options, what fields changed, and the running draft
— so you can watch the funnel narrow against the real job database.

Usage (from demo_real/):
    python test/guided_chat.py            # English (default)
    python test/guided_chat.py de         # German
    python test/guided_chat.py auto       # match your message language

Starts the Flask server itself if it isn't already running.

In-chat commands:
    1, 2, 3 …    pick a numbered quick option (sends its German taxonomy value)
    all          choose all offered options ("choose all")
    /lang en|de|auto   switch AI language mid-conversation
    /draft       print the full current draft as JSON
    /reset       start a fresh candidate
    /help        show these commands
    /quit        exit
"""
import sys
import os
import json
import time
import threading
import urllib.request
import urllib.error
import urllib.parse
import http.cookiejar

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Windows consoles default to cp1252 and choke on box-drawing / German chars.
for _stream in (sys.stdout, sys.stdin):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE = "http://localhost:5000"
URL  = f"{BASE}/api/guided/chat"

# The app requires a logged-in session; default seed account is admin/admin.
USER = os.getenv("JIA_USER", "admin")
PASS = os.getenv("JIA_PASS", "admin")

# A cookie-aware opener so the login session carries over to chat requests.
_opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

# ── tiny ANSI colour helpers (no-op if the terminal can't handle them) ─────────
def _c(code, s): return f"\033[{code}m{s}\033[0m"
def ai(s):     return _c("36", s)   # cyan
def q(s):      return _c("1;36", s)  # bold cyan
def you(s):    return _c("32", s)   # green
def dim(s):    return _c("90", s)   # grey
def warn(s):   return _c("33", s)   # yellow
def opt(s):    return _c("35", s)   # magenta

EMPTY_DRAFT = {
    "name": "", "roles": [], "skills": [], "levels": [], "states": [],
    "occ_groups": [], "languages": [], "certs": [], "salary": "",
    "availability": "", "notes": "",
}


def server_is_up():
    try:
        urllib.request.urlopen(f"{BASE}/", timeout=1)
        return True
    except Exception:
        return False


def start_server():
    import app as flask_app
    import config
    flask_app.app.run(host="0.0.0.0", port=config.FLASK_PORT, debug=False, use_reloader=False)


def ensure_server():
    if server_is_up():
        print(dim("Server already running."))
        return
    print(dim("Starting Flask server…"))
    threading.Thread(target=start_server, daemon=True).start()
    for _ in range(40):
        time.sleep(0.5)
        if server_is_up():
            print(dim("Server up."))
            return
    print(warn("Server didn't start in time. Is the DB/.env configured?"))
    sys.exit(1)


def login():
    """Establish a session cookie via the seed admin account."""
    data = urllib.parse.urlencode({"username": USER, "password": PASS}).encode("utf-8")
    try:
        with _opener.open(f"{BASE}/login", data=data, timeout=10) as resp:
            # On success the app redirects to "/"; a 200 on /login means it
            # re-rendered the form → bad credentials.
            if resp.geturl().rstrip("/").endswith("/login"):
                print(warn(f"  login failed for user '{USER}' — check JIA_USER / JIA_PASS."))
                return False
        return True
    except Exception as e:
        print(warn(f"  login error: {e}"))
        return False


def post_chat(message, draft, last_offer, lang, search_terms, last_question):
    body = json.dumps({
        "message": message, "draft": draft, "user_edits": [],
        "last_offer": last_offer, "lang": lang, "search_terms": search_terms,
        "last_question": last_question,
    }).encode("utf-8")
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    try:
        with _opener.open(req, timeout=90) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def draft_summary(draft):
    """One compact line per non-empty field."""
    lines = []
    for k, v in draft.items():
        if not v:
            continue
        val = ", ".join(v) if isinstance(v, list) else str(v)
        lines.append(f"    {k:<13} {val}")
    return "\n".join(lines) if lines else dim("    (empty)")


def print_help():
    print(dim(
        "  Commands: [number]=pick option · all=choose all · /lang en|de|auto · "
        "/draft · /reset · /help · /quit"))


def main():
    lang = sys.argv[1].lower() if len(sys.argv) > 1 else "en"
    if lang not in ("en", "de", "auto"):
        lang = "en"

    ensure_server()
    if not login():
        sys.exit(1)

    draft        = json.loads(json.dumps(EMPTY_DRAFT))
    last_offer   = None
    last_opts    = []   # [{value, label, n}] offered this turn, for numbered picks
    search_terms = []   # stable German role/sector stems driving the live count
    last_question = ""  # the assistant's previous question — keeps meta-Q on topic

    print()
    print(q("  Build-a-candidate live chat") + dim(f"   (AI lang: {lang})"))
    print_help()
    print(dim("  " + "─" * 60))
    print(ai("  assistant ▸ ") + "Hi — I'll help you build a target candidate. "
          "Which role(s) are you hiring for?")
    print()

    while True:
        try:
            raw = input(you("  you ▸ ")).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n" + dim("  bye."))
            return
        if not raw:
            continue

        # ── local commands ───────────────────────────────────────────────
        low = raw.lower()
        if low in ("/quit", "/exit", "/q"):
            print(dim("  bye.")); return
        if low == "/help":
            print_help(); continue
        if low == "/draft":
            print(dim(json.dumps(draft, indent=2, ensure_ascii=False))); continue
        if low == "/reset":
            draft = json.loads(json.dumps(EMPTY_DRAFT))
            last_offer = None; last_opts = []; search_terms = []; last_question = ""
            print(dim("  draft reset.")); continue
        if low.startswith("/lang"):
            parts = low.split()
            if len(parts) > 1 and parts[1] in ("en", "de", "auto"):
                lang = parts[1]; print(dim(f"  AI lang → {lang}"))
            else:
                print(warn("  usage: /lang en|de|auto"))
            continue

        # ── numbered pick → send that option's canonical (German) value ───
        message = raw
        if raw.isdigit() and last_opts:
            idx = int(raw) - 1
            if 0 <= idx < len(last_opts):
                message = last_opts[idx]["value"]
                print(dim(f"      ↳ picking: {last_opts[idx]['label']}  →  {message}"))
            else:
                print(warn(f"  no option #{raw}")); continue

        # ── call the endpoint ─────────────────────────────────────────────
        t0 = time.time()
        data = post_chat(message, draft, last_offer, lang, search_terms, last_question)
        dt = time.time() - t0

        if not data.get("ok"):
            print(warn(f"  error: {data.get('error')}")); print(); continue

        draft = data.get("draft", draft)
        if isinstance(data.get("search_terms"), list):
            search_terms = data["search_terms"]
        opts   = data.get("options") or []
        sugg   = data.get("suggestions") or []
        facets = data.get("facets") or {}
        changed = list((data.get("field_updates") or {}).keys())

        # assistant reply + question
        print()
        print(ai("  assistant ▸ ") + (data.get("reply") or ""))
        last_question = data.get("next_question") or ""
        if last_question:
            print(q("           ? ") + last_question)

        # quick-reply bubbles (numbered) — real data options, else suggestions
        if opts:
            last_opts = opts
            chips = "   ".join(opt(f"[{i+1}] {o['label']} ({o['n']})") for i, o in enumerate(opts))
        else:
            last_opts = [{"value": s, "label": s} for s in sugg]
            chips = "   ".join(opt(f"[{i+1}] {s}") for i, s in enumerate(sugg))
        if last_opts:
            print("           " + chips)
            print(dim("           type a number to pick" + (", or 'all'" if opts else "")))

        # remember what we offered, so "all" resolves next turn (data picks only)
        last_offer = ({"kind": data.get("facet"), "values": [o["value"] for o in opts]}
                      if opts and data.get("facet") else None)

        # diagnostics
        meta = []
        if facets.get("total"):
            meta.append(f"pool: {facets['total']} (role+region only)")
        if changed:
            meta.append("updated: " + ", ".join(changed))
        if search_terms:
            meta.append("terms: " + "/".join(search_terms))
        meta.append(f"{dt:.1f}s")
        print(dim("           (" + " · ".join(meta) + ")"))

        # running draft
        print(dim("  draft:"))
        print(dim(draft_summary(draft)))
        print()


if __name__ == "__main__":
    main()
