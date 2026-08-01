"""
launcher.py
------------
Single entry point for the packaged Windows executable. Starts the
FastAPI backend and the Streamlit frontend as background threads inside
ONE process, waits for both to come up, then opens the default browser
pointed at the Streamlit UI.

This is the file PyInstaller freezes (see build_windows.spec).
It also runs fine directly with `python launcher.py` from source,
which is the easiest way to test changes before building the .exe.
"""
from __future__ import annotations

import multiprocessing
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

# Must run before anything else when frozen on Windows (multiprocessing
# support for PyInstaller-built executables).
multiprocessing.freeze_support()

# Set BEFORE streamlit is imported anywhere, so it never shows the
# first-run "email address" prompt or phones home for usage stats.
os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
os.environ.setdefault("STREAMLIT_GLOBAL_DEVELOPMENT_MODE", "false")
# Streamlit's own upload cap defaults to 200MB regardless of the backend's
# own limit (backend/config.py Settings.max_upload_size_mb) — raise it to
# match so large Live_Data/Sold_Data files aren't rejected client-side.
os.environ.setdefault("STREAMLIT_SERVER_MAX_UPLOAD_SIZE", "500")

BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8000
FRONTEND_PORT = 8501

os.environ.setdefault("ATP_BACKEND_URL", f"http://{BACKEND_HOST}:{BACKEND_PORT}")


def _resource_path(relative_path: str) -> str:
    """
    Resolve a path that works both running from source AND from inside a
    PyInstaller-frozen executable (where files live under sys._MEIPASS).
    """
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def _run_backend() -> None:
    import uvicorn

    from backend.app import app as fastapi_app

    uvicorn.run(fastapi_app, host=BACKEND_HOST, port=BACKEND_PORT, log_level="warning")


def _run_frontend() -> None:
    from streamlit.web import cli as stcli

    script = _resource_path(os.path.join("frontend", "streamlit_app.py"))
    sys.argv = [
        "streamlit",
        "run",
        script,
        f"--server.port={FRONTEND_PORT}",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
        "--global.developmentMode=false",
    ]
    stcli.main()


def _wait_until_up(url: str, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.3)
    return False


def main() -> None:
    threading.Thread(target=_run_backend, daemon=True).start()
    if not _wait_until_up(f"http://{BACKEND_HOST}:{BACKEND_PORT}/api/v1/health"):
        print("ERROR: backend did not start in time.")
        return

    print("ATP Analyzer is starting...")
    print(f"  Backend:  http://{BACKEND_HOST}:{BACKEND_PORT}")
    print(f"  Frontend: http://127.0.0.1:{FRONTEND_PORT}  (opens automatically)")
    print("Close this window (or press Ctrl+C) to stop the application.")

    # Open the browser from a background thread once Streamlit is reachable —
    # the main thread is about to block inside Streamlit's own server loop.
    def _open_when_ready() -> None:
        if _wait_until_up(f"http://127.0.0.1:{FRONTEND_PORT}"):
            webbrowser.open(f"http://127.0.0.1:{FRONTEND_PORT}")

    threading.Thread(target=_open_when_ready, daemon=True).start()

    # Streamlit installs its own Ctrl+C / SIGTERM handlers, which only work
    # from the main thread of the main interpreter — so it MUST run here,
    # blocking, rather than in a background thread. This call doubles as
    # the whole application's "keep running until closed" loop.
    _run_frontend()


if __name__ == "__main__":
    main()
