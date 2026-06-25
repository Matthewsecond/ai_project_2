"""
Fixtures for the Playwright end-to-end (real-browser) frontend tests.

Unlike `integration_tests/` (Flask `test_client`, which never executes the page JS), these
tests drive a **real headless browser** against a live in-process server, so they actually run
the ~8,300-line client script. That's the only layer that can catch a broken cross-module
reference (the failure mode of the 2.6c ES-module split): a missing import throws an uncaught
exception in the browser, surfaced here via the `pageerror` event.

The server stubs the DB-backed auth (`init_db` / `verify_login`) so no MySQL is needed — login
is a real form POST, but credentials are checked against a fake admin instead of the database.
"""
import socket
import threading

import pytest
from werkzeug.serving import make_server


@pytest.fixture(scope="session")
def live_server():
    """A real Flask server in a background thread, auth stubbed (no DB). Yields its base URL."""
    import jobs_intelligence_ai.services.auth as auth
    from jobs_intelligence_ai import config

    _orig_init, _orig_verify = auth.init_db, auth.verify_login
    auth.init_db = lambda *a, **k: None
    auth.verify_login = lambda u, p: (
        {"id": 1, "username": u, "display_name": "Tester", "role": "admin"}
        if (u, p) == ("admin", "admin") else None
    )

    # Force every country feature flag ON so all tabs render — the smoke needs full
    # coverage (radar / map are the big modules in the 2.6c split). The context
    # processor reads these at request time, so patching the module attrs is enough.
    _orig_flags = {f: getattr(config, f) for f in ("HAS_MAP", "HAS_ANALYTICS", "HAS_GUIDED", "HAS_OCC_FILTER")}
    for f in _orig_flags:
        setattr(config, f, True)

    # create_app() does `from ...auth import init_db, verify_login` at call time, so the stubs
    # above (set first) are what it binds.
    from jobs_intelligence_ai.frontend.app import create_app
    app = create_app()
    app.config.update(TESTING=True)

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    server = make_server("127.0.0.1", port, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        auth.init_db, auth.verify_login = _orig_init, _orig_verify
        for f, v in _orig_flags.items():
            setattr(config, f, v)


@pytest.fixture
def logged_in_page(page, live_server):
    """A browser page that has cleared the login gate and is sitting on the app.

    A `pageerror` collector is attached *before* navigation so it captures load-time uncaught
    exceptions too; the collected list is exposed as `page.js_errors`.
    """
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.js_errors = errors

    page.goto(f"{live_server}/login")
    page.fill("#username", "admin")
    page.fill("#password", "admin")
    page.click("button[type=submit]")
    page.wait_for_url(f"{live_server}/")
    page.wait_for_selector("#tab-search", timeout=5000)
    return page
