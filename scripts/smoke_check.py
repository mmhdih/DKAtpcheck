"""
smoke_check.py
--------------
End-to-end check of a PACKAGED build, run by the Windows CI workflow after
it assembles the portable app and starts it (see
.github/workflows/build-windows.yml). Run it with the packaged app's own
python.exe, so it also proves that interpreter can import the bundled
dependencies.

It waits for the backend and the Streamlit frontend to come up, downloads
the Live_Data / Sold_Data templates, runs a real calculation with them,
and checks pandas' Styler (used by the results tables) works. Exits
non-zero on any failure, so a broken package is never published.
"""
from __future__ import annotations

import sys
import time

import requests

BACKEND = "http://127.0.0.1:8000/api/v1"
FRONTEND = "http://127.0.0.1:8501"


def _wait_for(url: str, label: str, timeout: float = 120.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if requests.get(url, timeout=3).status_code == 200:
                print(f"OK   {label} is up ({url})")
                return
        except requests.RequestException:
            pass
        time.sleep(1)
    raise SystemExit(f"FAIL {label} did not come up within {timeout:.0f}s ({url})")


def main() -> int:
    _wait_for(f"{BACKEND}/health", "backend")
    _wait_for(f"{FRONTEND}/_stcore/health", "frontend")

    live = requests.get(f"{BACKEND}/templates/live-data", timeout=30)
    sold = requests.get(f"{BACKEND}/templates/sold-data", timeout=30)
    live.raise_for_status()
    sold.raise_for_status()

    for metric in ("net_item", "nmv"):
        response = requests.post(
            f"{BACKEND}/calculate",
            files={
                "live_file": ("Live_Data.xlsx", live.content),
                "sold_file": ("Sold_Data.xlsx", sold.content),
            },
            data={"tolerance_pct": 10, "volume_metric": metric},
            timeout=120,
        )
        if response.status_code != 200:
            raise SystemExit(f"FAIL calculate ({metric}): HTTP {response.status_code}: {response.text[:500]}")
        body = response.json()
        if not body["summary"]:
            raise SystemExit(f"FAIL calculate ({metric}): empty summary")
        print(f"OK   calculation with {metric}: {len(body['summary'])} seller row(s)")

    import pandas as pd

    pd.DataFrame({"a": [1.0]}).style.format("{:.1f}").to_html()
    print("OK   pandas Styler (jinja2) works")

    print("Smoke test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
