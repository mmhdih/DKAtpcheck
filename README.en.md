# 📦 ATP Analyzer <sub>By Haj Mehdi</sub>

> 🇮🇷 Persian version (default): [README.md](README.md) — this file is the English version.

Calculates ATP (Available To Purchase) for marketplace sellers by comparing
a **Live_Data** export against a **Sold_Data** export.

- 🐍 **Backend**: FastAPI + pandas/numpy (Python 3.12+)
- 🎈 **Frontend**: Streamlit (thin client, no business logic)
- 📄 Both files can be uploaded as `.xlsx` or `.csv` (dispatched by filename
  extension), up to 500MB each by default (`ATP_MAX_UPLOAD_SIZE_MB`).
- ⚡ Built to comfortably handle ~500,000 Live_Data rows and ~30,000
  Sold_Data rows (see *Performance* below).

## ✨ Features

**What it does:** upload a **Live_Data** export (current live inventory)
and a **Sold_Data** export (sales), and it tells you — per sold item —
whether it's still **ATP (Available To Purchase)** right now, sliced and
filtered every way a merchandising team would need.

**🧮 What it can compute:**
- **DKPC-level ATP** (weight-aware): exact match, or a same-seller-**and**-same-DKP
  weight-tolerance match (configurable %).
- **DKP-level ATP** (weight-independent): is *any* variant of this product still live.
- A robust join between the two files via **Seller_ID** (not fuzzy seller-name matching).
- 🪙 ATP percentages split into **Bullion vs Jewelry** category buckets
  (user-configurable, with sensible defaults pre-selected), independently
  for DKPC and DKP.
- 🎯 **Item-Tail classification (ST/MT/LT)** — ABC/Pareto ranking by
  forecasted sales volume, marketplace-wide, computed **independently
  within each category bucket**, usable as a filter that affects the ATP
  percentages themselves.
- 📄 Reads both `.xlsx` and `.csv` uploads, up to 500MB per file.

**📤 What it can output (3 tabs in the UI):**
- 📊 **Summary** — one row per seller: 4 ATP percentages (Bullion/Jewelry × DKPC/DKP). Color-coded 🔴🟡🟢 on screen and in the downloaded `.xlsx`.
- 🔻 **Seller ATP Missing** — the full list of sold DKPCs that are NOT ATP, with category and bucket. Kept plain/uncolored on purpose, for easy reading of a raw list.
- 🎯 **Category ST/MT/LT PER Seller** — two outputs in one tab:
  - an **overall table**: DKP counts per seller, per tail badge, split into available/unavailable (color-coded);
  - an **item list**: every badged DKP across *all* sellers combined in a single flat `.xlsx` (color-coded by badge/status) — no per-seller split, just the raw list.
- 📦 **Per-seller ZIP export** (opt-in) — one `SellerID-SellerName.xlsx` per
  seller listing their unavailable items (weight, category, bucket, tail
  badge included), ready to email straight to each seller.
- 📋 **Downloadable templates** — example Live_Data/Sold_Data files with the correct headers, no guessing column names.
- 🎨 Every colored table above is also colored the same way in its downloaded `.xlsx` file — not just on screen.

## 🗂️ Project structure

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
│   ├── tail_classifier.py      ST/MT/LT Item-Tail classification (ABC/Pareto)
│   ├── summary_generator.py    builds the Summary table
│   ├── missing_generator.py    builds the ATP_Missing table
│   ├── tail_summary_generator.py builds the Category ST/MT/LT tables (overall counts + flat DKP list)
│   ├── seller_export.py        per-seller NOT-ATP ZIP export
│   └── templates.py            downloadable example Live_Data/Sold_Data templates
├── frontend/
│   └── streamlit_app.py        upload UI, filters, results, downloads
├── tests/
├── conftest.py
└── requirements.txt
```

## ⚙️ Setup

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## ▶️ Running

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

## 🧪 Running the tests

```bash
python -m pytest tests/ -v
```

## 🔗 Column mapping

`Seller_ID` / `marketplace_seller_id` is the **join key** between the two
files (matched after normalization/casefolding) — seller *name* is kept
purely for display and is never used to match rows across files.

| Live_Data column | Sold_Data column | Canonical field | Notes |
|---|---|---|---|
| `Seller_ID` | `marketplace_seller_id` | `seller_id` | join key |
| `Seller_Name` | `marketplace_seller_name` | `seller` | display only |
| `DKP` | `product_id` | `dkp` | |
| `DKPC` | `product_variant_id` | `dkpc` | |
| `Size_Name` | `product_variant_name_fa` | `weight` | parsed via the same numeric/"`<n> گرم`" logic on both sides |
| — | `category_name_fa` | `category` | Sold_Data only; drives the Bullion/Jewelry bucket |
| — | `sum_net_item_fcast` | `net_item_fcast` | Sold_Data only; drives the ST/MT/LT tail badge |

Both uploaded files' required columns are validated on upload; download
example templates straight from the app (`⬇ Live_Data template` /
`⬇ Sold_Data template` buttons, or `GET /api/v1/templates/live-data` /
`GET /api/v1/templates/sold-data`) so column names never have to be
guessed.

## 🧮 How matching works

For every **unique** sold DKPC (repeat sales of the same DKPC count once):

1. **Exact match** — if that DKPC exists live under the same seller → ATP.
2. **Weight tolerance** — only if step 1 failed *and* a weight could be
   parsed from `product_variant_name_fa`: ATP if any live DKPC of the
   same seller **and the same DKP** has a weight within `± tolerance%` of
   the sold weight. The tolerance search is scoped to the same product —
   a live item of a *different* DKP never grants ATP just because its
   weight happens to be close.
3. If no weight could be parsed, only step 1 applies (no fallback).

**DKP-level ATP** is computed independently and is weight-agnostic: a sold
DKP is ATP if the seller has *any* live DKPC under that DKP.

Tolerance is a request parameter, not hardcoded — pass `0` for exact-only
matching, or any value the seller wants to try.

## 🪙 Category buckets (Bullion vs Jewelry)

The Summary table splits DKPC/DKP ATP% into two independently-computed
buckets: **Bullion** (شمش) and **Jewelry** (زیور). Which `category_name_fa`
values count as Bullion is chosen per calculation (`bullion_categories`
request field) — fetch the distinct categories found in an uploaded
Sold_Data file via `POST /api/v1/sold-data/categories` to populate a
picker before running the calculation. Any category not explicitly marked
Bullion (including blank/missing categories) is treated as Jewelry.

## 🎯 Item-Tail classification (ST/MT/LT)

Every sold DKP is ranked **marketplace-wide** (across every seller
combined, not per seller) by its total `sum_net_item_fcast` — but
**separately within each category bucket**: Bullion DKPs are ranked only
against other Bullion DKPs, and Jewelry DKPs only against other Jewelry
DKPs, so one bucket's volume never affects the other bucket's cutoffs.
Within each bucket, a standard ABC/Pareto cumulative-share cutoff applies:
the top DKPs making up the first 30% of that bucket's forecasted item
volume get **ST**, the next 40% (30–70%) get **MT**, and the remaining
30% get **LT**. All DKPCs under a badged DKP inherit that DKP's badge.
DKPs whose total `sum_net_item_fcast` is zero or entirely blank get **no
badge at all** (they're excluded from the ranking, not defaulted to LT).
`tail_badges` is a request field (default: all three, i.e. no filtering)
— filtering happens *before* the ATP calculation, so it changes the
Summary percentages too, not just
which rows are displayed.

## 📦 Per-seller missing-items ZIP export

Set `generate_seller_zip=true` on `/calculate` to also build a ZIP
(downloaded via `GET /api/v1/download/seller-zip/{result_id}`) containing
one `SellerID-SellerName.xlsx` per seller — that seller's NOT-ATP DKPCs
with Weight, Category, Bucket, and Tail Badge, sorted by that row's own
`sum_net_item_fcast` descending (the number itself isn't included in the
output; rows with a zero/blank value are excluded entirely). Meant for
emailing each seller their own actionable list. It's opt-in and only
built when requested, since it's extra work on top of the normal
Summary/Missing calculation.

## 🎯 Category ST/MT/LT per Seller (two outputs, one tab)

The third UI tab (**"🎯 Category ST/MT/LT PER Seller"**) has two independent outputs:

1. **Overall table** — `tail_summary` response field / `GET
   /api/v1/download/tail-summary/{result_id}` (`Tail_Summary.xlsx`). Per
   seller, how many of their sold DKPs in each Item-Tail bucket are
   currently ATP (available) vs NOT ATP (unavailable) — e.g. `ST
   Available`, `ST Unavailable`, `MT Available`, `MT Unavailable`, `LT
   Available`, `LT Unavailable`. DKP-level (weight-independent) counts,
   since the badge itself is a DKP-level concept. Sellers with no badged
   DKPs at all are omitted.
2. **Item list** — `GET /api/v1/download/tail-dkp-list/{result_id}`
   (`Tail_DKP_List.xlsx`). Every badged DKP across **all** sellers
   combined, in one flat file — Seller ID, Seller, DKP, Category, Bucket,
   Tail Badge, Status (Available/Unavailable). Not split per seller (use
   the ZIP export above if you need a per-seller split instead).

## 🎨 Colored outputs

The Summary tab/file and the Category ST/MT/LT overall table/file use a
🔴🟡🟢 red→yellow→green color scale (same visual language on screen and
in the downloaded `.xlsx`, via openpyxl conditional formatting). The
Category ST/MT/LT item-list file uses solid categorical colors instead
(ST=green, MT=yellow, LT=red; Available=green, Unavailable=red). **Seller
ATP Missing is deliberately left uncolored** — it's meant to be read as a
plain, scannable raw list.

## 🚀 Performance

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

## 🧩 Adding a new ATP rule

DKPC-level matching is an ordered rule pipeline (`atp_engine.ATPRule`).
To add a rule:

```python
from backend.atp_engine import ATPRule
from backend.models import ATPMatchType

class MyNewRule(ATPRule):
    match_type = ATPMatchType.SOME_NEW_TYPE  # add to the enum in models.py

    def evaluate(self, *, seller_key, dkp, dkpc, weight, index) -> bool:
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

## 🔧 Configuration reference (environment variables, prefix `ATP_`)

| Variable | Default | Purpose |
|---|---|---|
| `ATP_CORS_ALLOW_ORIGINS` | `["*"]` | CORS origins allowed to call the API |
| `ATP_TOLERANCE_PRESETS` | `[0,5,10,15,20]` | Quick-select buttons in the UI (not a hard limit) |
| `ATP_DEFAULT_TOLERANCE_PCT` | `10.0` | Pre-filled tolerance value |
| `ATP_MAX_UPLOAD_SIZE_MB` | `500` | Rejects larger uploads with HTTP 413 |
| `ATP_EXCEL_ENGINE_PREFERENCE` | `["calamine","openpyxl"]` | Excel read engine order |
| `ATP_CSV_EXTENSIONS` | `[".csv"]` | Filename extensions read as CSV instead of Excel |
| `ATP_CSV_ENCODING_PREFERENCE` | `["utf-8-sig","cp1256","utf-8"]` | CSV text encodings to try, in order |
| `ATP_RESULT_CACHE_TTL_SECONDS` | `1800` | How long a calculated result stays downloadable |
| `ATP_RESULT_CACHE_MAX_ENTRIES` | `50` | Oldest result evicted once exceeded |
| `ATP_LOG_LEVEL` | `INFO` | Backend log verbosity |

`ATP_MAX_UPLOAD_SIZE_MB` only governs the FastAPI backend's own check.
Streamlit enforces its own upload cap independently (default 200MB) —
this repo's `.streamlit/config.toml` (`server.maxUploadSize`) and
`launcher.py` (the packaged .exe entry point) both raise it to match, so
raise both together if you increase the limit further.

There are no environment variables for the ST/MT/LT cumulative cutoffs
(30%/70%) — they're fixed constants (`config.TailClassification`), not
runtime-configurable, per the spec.

The result cache is in-memory and assumes a single backend process. If
you ever run multiple workers/instances behind a load balancer, swap
`utils.ResultCache` for a shared store (Redis, a database) behind the
same `put()`/`get()` interface — nothing else needs to change.

## 📝 Known assumptions

- `Seller_ID` (`marketplace_seller_id` in Sold_Data) is the join key
  between the two files — matched after normalization and casefolding
  (`seller_key` internally). Seller *name* is never used to match rows;
  it's kept only for display, independently per file.
- `Seller_ID`/`DKP`/`DKPC` are normalized with `normalize_id`, which
  strips a trailing `.0` from integer-valued values — this guards against
  the common Excel gotcha where an ID column gets upcast to float64
  (e.g. `20911381.0`) just because some other cell in that column is
  blank.
- `product_variant_name_fa` in Sold_Data is parsed the same way as
  `Size_Name` in Live_Data (plain numbers and `"<number> گرم"` text are
  both accepted).
- A `category_name_fa` value that's blank or not explicitly marked as
  Bullion defaults to the Jewelry bucket.
- A DKP's category bucket (for the DKP-level Summary split) is taken from
  whichever of its sold DKPCs appears first in the file — the same
  "first-seen" approximation already used for seller display-name
  casing. If a single DKP's variants are genuinely split across both
  buckets in practice, this picks one rather than splitting the DKP
  itself.
- Rows with a zero or blank `sum_net_item_fcast` are excluded entirely
  from Item-Tail ranking (no badge at all, not defaulted to LT) and from
  the per-seller ZIP export — they're not merely sorted last.
- The frontend's Bullion-labels picker defaults to pre-selecting
  `شمش طلا`, `پک شمش و پلاک طلا`, `سکه و شمش نقره`, and
  `سکه پارسیان (گرمی)` whenever they appear in the uploaded Sold_Data's
  categories (`frontend/streamlit_app.py::DEFAULT_BULLION_CATEGORIES`) —
  still fully editable per calculation, this is just the starting point.
- CSV uploads try `utf-8-sig` → `cp1256` → `utf-8` encodings in order and
  auto-detect the delimiter (Iranian Excel exports mix `,` and `;`
  depending on regional settings) — see `ATP_CSV_ENCODING_PREFERENCE`.

## 💻 Packaging as a Windows .exe

> 🚀 **Don't want to build it yourself?** Grab the latest portable,
> no-install-needed build straight from this repo's **[Releases](../../releases)**
> page — extract the zip and double-click `ATP_Analyzer.exe`.

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
