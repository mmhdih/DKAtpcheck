# ATP Analyzer

Calculates ATP (Available To Purchase) for marketplace sellers by comparing
a **Live_Data** Excel export against a **Sold_Data** Excel export.

- **Backend**: FastAPI + pandas/numpy (Python 3.12+)
- **Frontend**: Streamlit (thin client, no business logic)
- Built to comfortably handle ~500,000 Live_Data rows and ~30,000
  Sold_Data rows (see *Performance* below).

## Project structure

```
atp_analyzer/
├── backend/
│   ├── app.py                 FastAPI routes
│   ├── config.py              column names, defaults, runtime settings
│   ├── models.py               Pydantic request/response schemas
│   ├── utils.py                logging, normalization, result cache, Excel export
│   ├── weight_parser.py        extracts weight from "... | 0.65 گرم |"
│   ├── excel_loader.py          reads & validates both Excel files
│   ├── atp_engine.py           the ATP rule pipeline (the core)
│   ├── summary_generator.py    builds the Summary table
│   └── missing_generator.py    builds the ATP_Missing table
├── frontend/
│   └── streamlit_app.py        upload UI, results, downloads
├── tests/
├── conftest.py
└── requirements.txt
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Running

Start the backend (from the project root):

```bash
uvicorn backend.app:app --reload --port 8000
```

In a second terminal, start the frontend:

```bash
streamlit run frontend/streamlit_app.py
```

Open the URL Streamlit prints (usually `http://localhost:8501`). If the
backend runs somewhere other than `localhost:8000`, set:

```bash
export ATP_BACKEND_URL=http://your-backend-host:8000
```

## Running the tests

```bash
python -m pytest tests/ -v
```

## How matching works

For every **unique** sold DKPC (repeat sales of the same DKPC count once):

1. **Exact match** — if that DKPC exists live under the same seller → ATP.
2. **Weight tolerance** — only if step 1 failed *and* a weight could be
   parsed from `Product Item Name`: ATP if any live DKPC of the same
   seller has a weight within `± tolerance%` of the sold weight.
3. If no weight could be parsed, only step 1 applies (no fallback).

**DKP-level ATP** is computed independently and is weight-agnostic: a sold
DKP is ATP if the seller has *any* live DKPC under that DKP.

Tolerance is a request parameter, not hardcoded — pass `0` for exact-only
matching, or any value the seller wants to try.

## Performance

The two datasets are read once each and turned into per-seller lookup
structures — no nested loop over Live_Data rows:

- `dkpc_by_seller` / `dkp_by_seller`: `dict[str, set]` → O(1) exact-match checks.
- `weights_by_seller`: a **sorted** NumPy array per seller. A tolerance
  check is a binary search (`np.searchsorted`) for "is any live weight in
  `[lo, hi]`", i.e. O(log n) instead of comparing against every live row.

On a synthetic 500,000-row Live_Data / 30,000-row Sold_Data / 1,000-seller
dataset, the full pipeline (Excel read → index build → ATP compute →
report generation → Excel export) completes in well under 15 seconds on a
single core, with the actual matching step taking a fraction of a second.

Excel reading prefers the Rust-backed `calamine` engine and falls back to
`openpyxl` automatically if `calamine` is unavailable or fails to parse a
given file — no code changes needed either way.

## Adding a new ATP rule

DKPC-level matching is an ordered rule pipeline (`atp_engine.ATPRule`).
To add a rule:

```python
from backend.atp_engine import ATPRule
from backend.models import ATPMatchType

class MyNewRule(ATPRule):
    match_type = ATPMatchType.SOME_NEW_TYPE  # add to the enum in models.py

    def evaluate(self, *, seller_key, dkpc, weight, index) -> bool:
        ...  # your logic, using `index` (the ATPIndex) as needed
```

Then pass it in when building the engine:

```python
from backend.atp_engine import ATPEngine, default_dkpc_rules

engine = ATPEngine(
    index=index,
    tolerance_pct=tolerance_pct,
    dkpc_rules=[*default_dkpc_rules(tolerance_pct), MyNewRule()],
)
```

Nothing else in the pipeline (deduplication, summary/missing generation,
the API layer) needs to change.

## Configuration reference (environment variables, prefix `ATP_`)

| Variable | Default | Purpose |
|---|---|---|
| `ATP_CORS_ALLOW_ORIGINS` | `["*"]` | CORS origins allowed to call the API |
| `ATP_TOLERANCE_PRESETS` | `[0,5,10,15,20]` | Quick-select buttons in the UI (not a hard limit) |
| `ATP_DEFAULT_TOLERANCE_PCT` | `10.0` | Pre-filled tolerance value |
| `ATP_MAX_UPLOAD_SIZE_MB` | `100` | Rejects larger uploads with HTTP 413 |
| `ATP_EXCEL_ENGINE_PREFERENCE` | `["calamine","openpyxl"]` | Excel read engine order |
| `ATP_RESULT_CACHE_TTL_SECONDS` | `1800` | How long a calculated result stays downloadable |
| `ATP_RESULT_CACHE_MAX_ENTRIES` | `50` | Oldest result evicted once exceeded |
| `ATP_LOG_LEVEL` | `INFO` | Backend log verbosity |

The result cache is in-memory and assumes a single backend process. If
you ever run multiple workers/instances behind a load balancer, swap
`utils.ResultCache` for a shared store (Redis, a database) behind the
same `put()`/`get()` interface — nothing else needs to change.

## Known assumptions

- Seller names are matched case-insensitively and whitespace-trimmed
  (`seller_key` internally); the seller's own casing from each file is
  preserved for display in that file's output.
- `Size_Name` in Live_Data is parsed the same way as `Product Item Name`
  in Sold_Data (plain numbers and `"<number> گرم"` text are both
  accepted).

## Packaging as a Windows .exe

There are two ways to get `ATP_Analyzer.exe`: build it locally on a
Windows machine, or let GitHub build it for you in the cloud (useful if
your machine is company-managed and locked down — no admin rights,
registry edits, or local Python installation needed).

### Option A — Let GitHub build it for you (no local build, no admin rights)

A ready-made workflow (`.github/workflows/build-windows.yml`) is already
included. It spins up a clean, disposable Windows machine on GitHub's
servers, builds the app there with a normal Python installation (not the
Microsoft Store version, so none of its long-path/permission quirks
apply), and hands you a downloadable .exe. None of this touches your own
computer.

1. Create a free account at [github.com](https://github.com) if you
   don't have one.
2. Click **+ → New repository** (top right). Give it any name (e.g.
   `atp-analyzer`), keep it Public or Private, then **Create repository**.
3. On the new repo's page, click **"uploading an existing file"** (or
   **Add file → Upload files**). Drag in the *entire contents* of this
   project folder (everything inside the zip you were given — `backend/`,
   `frontend/`, `.github/`, `requirements.txt`, `build_windows.spec`,
   etc.). This works entirely from the browser — no `git` command needed.
4. Commit the upload ("Commit changes").
5. Go to the **Actions** tab of your new repo. A run named
   *"Build Windows executable"* should already be starting (it triggers
   automatically on upload). If it isn't there, click the workflow on the
   left, then **"Run workflow"**.
6. Wait for the green checkmark (a few minutes).
7. Click into the finished run, scroll to **Artifacts** at the bottom,
   and download **ATP_Analyzer-windows** — this is your built app as a
   .zip.
8. Extract it anywhere on your Windows machine and double-click
   `ATP_Analyzer.exe`.

If your company network blocks github.com, try this from a personal
device/network instead — you only need GitHub to *build* it; the
resulting .exe runs on any Windows machine afterwards, including the
locked-down one.

### Option B — Build locally on Windows

`launcher.py` is a single entry point that starts the FastAPI backend and
the Streamlit frontend as one process and opens your browser — this is
what gets frozen into the .exe.

**You must build ON Windows** (PyInstaller does not cross-compile — a
Linux or Mac machine can't produce a Windows .exe).

Copy this project folder onto the Windows machine, then from the project
root run:

```bat
build_windows.bat
```

That script creates a virtualenv, installs `requirements.txt` +
`pyinstaller`, and runs `pyinstaller build_windows.spec`. The result is a
folder:

```
dist\ATP_Analyzer\
    ATP_Analyzer.exe
    ... (dependencies)
```

Double-click `ATP_Analyzer.exe` — it starts both servers in the background
and opens your default browser to the app. **Distribute the whole
`dist\ATP_Analyzer` folder**, not just the .exe file; the process needs
the files sitting next to it.

Manual equivalent, if you'd rather not use the .bat file:

```bat
pip install -r requirements.txt
pip install pyinstaller
pyinstaller --noconfirm build_windows.spec
```

### Why a .spec file instead of plain `pyinstaller launcher.py`

Streamlit ships its compiled frontend (HTML/JS/CSS) as package data, not
Python source — a plain PyInstaller run won't find it, and the app will
fail immediately with missing-file errors. `build_windows.spec` uses
`collect_all(...)` for streamlit, pandas, fastapi, uvicorn, and the other
libraries with the same issue, so all their non-`.py` assets are bundled
automatically.

### Troubleshooting

- **`OSError: [Errno 2] No such file or directory` mentioning a path like
  `AppData\Local\Packages\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\...`**:
  this means Python was installed from the Microsoft Store, whose deeply
  nested install path combined with Streamlit's own nested package files
  exceeds Windows' 260-character path limit — this is a known, common
  issue (it happens with several other large packages too, not just
  Streamlit) and isn't specific to this project. On a restricted/managed
  machine where you can't install a different Python or edit the
  registry, use **Option A above** (GitHub builds it for you) instead.
- **Antivirus flags the .exe / SmartScreen warning**: this is normal and
  expected for unsigned PyInstaller executables; it's not a bug in the
  app. Code-sign the binary if you're distributing it publicly.
- **"Could not find module" at runtime**: add the missing package's name
  to `COLLECT_ALL_PACKAGES` in `build_windows.spec` and rebuild.
- **Large output folder / slow first launch**: onedir (used here) is much
  faster to start than `--onefile`, at the cost of a bigger folder rather
  than a single file. Stick with onedir unless you specifically need a
  single-file artifact.
- **Want to hide the console window**: set `console=False` in
  `build_windows.spec` once you've confirmed everything works with it
  visible — the console is invaluable for reading the first few errors.
- **Want a proper desktop window instead of a browser tab**: swap
  `webbrowser.open(...)` in `launcher.py` for a
  [`pywebview`](https://pywebview.flowrl.com/) window pointed at the same
  URL. Not included by default to keep the packaging surface smaller.
