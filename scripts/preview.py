"""
preview.py — Opens the job detail view in your browser with a fixture job.

Usage (from demo_real/):
    python test/preview.py        # shows fixture 0 (Staplerfahrer)
    python test/preview.py 1      # fixture 1 (Software Developer)
    python test/preview.py 2      # fixture 2 (Koch)
    python test/preview.py 3      # fixture 3 (DGKP nurse)
    python test/preview.py 4      # fixture 4 (Reinigungskraft)

Starts the Flask server if it isn't already running, then opens the browser.
"""
import sys
import os
import time
import threading
import webbrowser
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

N = int(sys.argv[1]) if len(sys.argv) > 1 else 0
URL = f"http://localhost:5000/test/job-detail/{N}"


def server_is_up():
    try:
        urllib.request.urlopen("http://localhost:5000/", timeout=1)
        return True
    except Exception:
        return False


def start_server():
    import app as flask_app
    from jobs_intelligence_ai import config
    flask_app.app.run(host="0.0.0.0", port=config.FLASK_PORT, debug=False, use_reloader=False)


if not server_is_up():
    print("Starting Flask server…")
    t = threading.Thread(target=start_server, daemon=True)
    t.start()
    for _ in range(20):
        time.sleep(0.5)
        if server_is_up():
            break
    else:
        print("Server didn't start in time — open manually:", URL)
        sys.exit(1)
else:
    print("Server already running.")

print(f"Opening fixture {N}: {URL}")
webbrowser.open(URL)

# Keep alive so server stays up until you close the terminal
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nDone.")
