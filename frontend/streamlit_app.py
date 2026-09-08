"""
streamlit_app.py
------------------
Thin UI client for the ATP Analyzer FastAPI backend. Contains no business
logic: it uploads the two Excel files, lets the user set the weight
tolerance plus the Bullion/Jewelry category split and Item-Tail (ST/MT/LT)
filters, calls the backend, and renders the Summary / ATP_Missing results
with download buttons (including the optional per-seller ZIP export).

Run with:
    streamlit run frontend/streamlit_app.py

Configure the backend location with the ATP_BACKEND_URL environment
variable (defaults to http://localhost:8000).
"""
from __future__ import annotations

import os

import pandas as pd
import requests
import streamlit as st

try:
    import matplotlib  # noqa: F401

    _MATPLOTLIB_AVAILABLE = True
except ImportError:
    _MATPLOTLIB_AVAILABLE = False

BACKEND_URL = os.environ.get("ATP_BACKEND_URL", "http://localhost:8000").rstrip("/")
API = f"{BACKEND_URL}/api/v1"

st.set_page_config(page_title="ATP Analyzer By Haj Mehdi", page_icon="📦", layout="wide")

CUSTOM_CSS = """
<style>
    #MainMenu, footer {visibility: hidden;}
    .block-container {padding-top: 2.2rem; max-width: 1150px;}

    .atp-hero {
        padding: 1.4rem 1.6rem;
        border-radius: 14px;
        background: linear-gradient(135deg, #1F2937 0%, #374151 100%);
        color: #F9FAFB;
        margin-bottom: 1.4rem;
    }
    .atp-hero h1 {font-size: 1.6rem; margin: 0 0 0.2rem 0; font-weight: 700;}
    .atp-hero p {margin: 0; opacity: 0.85; font-size: 0.95rem;}

    .atp-hero-links {margin-top: 0.75rem; font-size: 0.88rem;}
    .atp-hero-links a {
        color: #F9FAFB !important;
        text-decoration: none !important;
        opacity: 0.8;
        border-bottom: 1px solid rgba(249, 250, 251, 0.35);
    }
    .atp-hero-links a:hover {opacity: 1; border-bottom-color: #F9FAFB;}
    .atp-hero-links span {opacity: 0.45; margin: 0 0.5rem;}

    .atp-card {
        background: #FFFFFF;
        border: 1px solid #E5E7EB;
        border-radius: 12px;
        padding: 1.1rem 1.3rem;
        margin-bottom: 1rem;
    }

    div[data-testid="stMetric"] {
        background: #F9FAFB;
        border: 1px solid #E5E7EB;
        border-radius: 10px;
        padding: 0.7rem 0.9rem;
    }

    .stButton>button, .stDownloadButton>button {
        border-radius: 8px;
        font-weight: 600;
    }

    .atp-footer {
        margin-top: 2.5rem;
        padding-top: 1.3rem;
        border-top: 1px solid #E5E7EB;
        text-align: center;
        color: #6B7280;
        font-size: 0.9rem;
    }
    .atp-footer-links {
        display: flex;
        gap: 0.6rem;
        justify-content: center;
        flex-wrap: wrap;
        margin-top: 0.8rem;
    }
    .atp-footer-links a {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        padding: 0.45rem 0.95rem;
        border-radius: 8px;
        border: 1px solid #E5E7EB;
        background: #FFFFFF;
        color: #1F2937 !important;
        text-decoration: none !important;
        font-weight: 600;
    }
    .atp-footer-links a:hover {background: #F9FAFB; border-color: #9CA3AF;}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

GITHUB_URL = "https://github.com/mmhdih"
TELEGRAM_HANDLE = "@mmhdih"
TELEGRAM_URL = "https://t.me/mmhdih"

st.markdown(
    f"""
    <div class="atp-hero">
        <h1>📦 ATP Analyzer By Haj Mehdi</h1>
        <p>Upload Live_Data and Sold_Data to find out which sold products are Available To Purchase.</p>
        <div class="atp-hero-links">
            <a href="{GITHUB_URL}" target="_blank" rel="noopener noreferrer">GitHub</a>
            <span>·</span>
            <a href="{TELEGRAM_URL}" target="_blank" rel="noopener noreferrer">Telegram {TELEGRAM_HANDLE}</a>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

TAIL_BADGE_OPTIONS = ["ST", "MT", "LT"]

DEFAULT_BULLION_CATEGORIES = [
    "شمش طلا",
    "پک شمش و پلاک طلا",
    "سکه و شمش نقره",
    "سکه پارسیان (گرمی)",
]


@st.cache_data(ttl=60, show_spinner=False)
def _fetch_backend_config() -> dict:
    resp = requests.get(f"{API}/config", timeout=10)
    resp.raise_for_status()
    return resp.json()


@st.cache_data(ttl=5, show_spinner=False)
def _fetch_field_names() -> dict:
    resp = requests.get(f"{API}/field-names", timeout=10)
    resp.raise_for_status()
    return resp.json()


def _save_field_names(values: dict[str, str]) -> dict:
    resp = requests.post(f"{API}/field-names", json={"values": values}, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _reset_field_names() -> dict:
    resp = requests.post(f"{API}/field-names/reset", timeout=10)
    resp.raise_for_status()
    return resp.json()


@st.cache_data(show_spinner=False)
def _fetch_template(kind: str) -> bytes:
    resp = requests.get(f"{API}/templates/{kind}", timeout=30)
    resp.raise_for_status()
    return resp.content


@st.cache_data(show_spinner=False)
def _fetch_categories(sold_bytes: bytes, filename: str) -> list[str]:
    resp = requests.post(
        f"{API}/sold-data/categories", files={"sold_file": (filename, sold_bytes)}, timeout=60
    )
    resp.raise_for_status()
    return resp.json()["categories"]


try:
    backend_cfg = _fetch_backend_config()
except requests.RequestException:
    st.error(
        f"Can't reach the ATP Analyzer backend at `{BACKEND_URL}`. "
        "Make sure it's running (`uvicorn backend.app:app`)."
    )
    st.stop()

# --------------------------------------------------------------------------- #
# Settings — editable raw column names, persisted locally on this machine
# --------------------------------------------------------------------------- #
with st.expander("⚙️ تنظیمات — نام ستون‌های اکسل (Settings — column names)", expanded=False):
    st.caption(
        "اگه فروشنده اسم یکی از ستون‌های Live_Data یا Sold_Data رو تغییر داد (مثلاً ستون وزن)، "
        "می‌تونی همینجا اصلاحش کنی. مقادیر روی همین سیستم ذخیره می‌شن و دیگه لازم نیست هر بار "
        "دوباره وارد کنی."
    )
    try:
        field_names_cfg = _fetch_field_names()
    except requests.RequestException as exc:
        field_names_cfg = None
        st.warning(f"تنظیمات نام ستون‌ها در دسترس نیست: {exc}")

    if field_names_cfg:
        with st.form("field_names_form"):
            live_fields = [f for f in field_names_cfg["fields"] if f["key"].startswith("live_")]
            sold_fields = [f for f in field_names_cfg["fields"] if f["key"].startswith("sold_")]

            fcol_live, fcol_sold = st.columns(2)
            new_values: dict[str, str] = {}
            with fcol_live:
                st.markdown("**Live_Data**")
                for f in live_fields:
                    new_values[f["key"]] = st.text_input(
                        f["label"], value=f["value"], key=f"field_name_{f['key']}"
                    )
            with fcol_sold:
                st.markdown("**Sold_Data**")
                for f in sold_fields:
                    new_values[f["key"]] = st.text_input(
                        f["label"], value=f["value"], key=f"field_name_{f['key']}"
                    )

            bcol1, bcol2 = st.columns(2)
            save_clicked = bcol1.form_submit_button("💾 ذخیره", use_container_width=True)
            reset_clicked = bcol2.form_submit_button(
                "↩️ بازگردانی به پیش‌فرض", use_container_width=True
            )

        if save_clicked:
            try:
                _save_field_names(new_values)
                _fetch_field_names.clear()
                st.success("تنظیمات ذخیره شد.")
                st.rerun()
            except requests.RequestException as exc:
                st.error(f"ذخیره تنظیمات با خطا مواجه شد: {exc}")

        if reset_clicked:
            try:
                _reset_field_names()
                _fetch_field_names.clear()
                st.success("نام ستون‌ها به پیش‌فرض بازگشت.")
                st.rerun()
            except requests.RequestException as exc:
                st.error(f"بازگردانی با خطا مواجه شد: {exc}")

# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #
col_left, col_right = st.columns(2, gap="large")

with col_left:
    st.markdown('<div class="atp-card">', unsafe_allow_html=True)
    st.subheader("1. Upload files")
    live_file = st.file_uploader("Live_Data.xlsx or .csv", type=["xlsx", "csv"], key="live_file")
    sold_file = st.file_uploader("Sold_Data.xlsx or .csv", type=["xlsx", "csv"], key="sold_file")

    tcol1, tcol2 = st.columns(2)
    try:
        tcol1.download_button(
            "⬇ Live_Data template", data=_fetch_template("live-data"),
            file_name="Live_Data_Template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
        tcol2.download_button(
            "⬇ Sold_Data template", data=_fetch_template("sold-data"),
            file_name="Sold_Data_Template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    except requests.RequestException:
        st.caption("Templates unavailable — backend unreachable.")
    st.markdown("</div>", unsafe_allow_html=True)

with col_right:
    st.markdown('<div class="atp-card">', unsafe_allow_html=True)
    st.subheader("2. Weight tolerance")
    presets = backend_cfg["tolerance_presets"]
    preset_labels = [f"{int(p) if p == int(p) else p}%" for p in presets] + ["Custom"]
    choice = st.radio("Quick select", preset_labels, horizontal=True, index=len(presets) // 2, label_visibility="collapsed")

    if choice == "Custom":
        tolerance_pct = st.number_input(
            "Custom tolerance %", min_value=0.0, max_value=100.0,
            value=backend_cfg["default_tolerance_pct"], step=0.5,
        )
    else:
        tolerance_pct = presets[preset_labels.index(choice)]
        st.caption(f"Using {tolerance_pct}% tolerance. A sold DKPC matches if a live item of the same seller AND same DKP falls within ±{tolerance_pct}% of its weight.")
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown('<div class="atp-card">', unsafe_allow_html=True)
st.subheader("3. Categories & Item-Tail filters")

bullion_categories: list[str] = []
if sold_file is not None:
    try:
        categories = _fetch_categories(sold_file.getvalue(), sold_file.name)
        default_bullion = [c for c in DEFAULT_BULLION_CATEGORIES if c in categories]
        bullion_categories = st.multiselect(
            "لیبل‌های شمش (Bullion labels) — everything else is treated as Jewelry",
            options=categories, default=default_bullion,
        )
    except requests.RequestException as exc:
        st.warning(f"Couldn't preview Sold_Data categories yet: {exc}")
else:
    st.caption("Upload Sold_Data above to choose which categories count as Bullion.")

tail_badges = st.multiselect(
    "Item-Tail badges to include (ST/MT/LT, ranked by sum_net_item_fcast marketplace-wide, separately for Bullion and Jewelry)",
    options=TAIL_BADGE_OPTIONS, default=TAIL_BADGE_OPTIONS,
)
generate_seller_zip = st.checkbox("Also generate the per-seller missing-items ZIP export (for emailing to sellers)")
generate_seller_tail_zip = st.checkbox(
    "Also generate the per-seller ZIP export of the Per-Seller Item-Tail tab (one xlsx per seller)"
)
st.markdown("</div>", unsafe_allow_html=True)

run_clicked = st.button("▶ Run calculation", type="primary", use_container_width=True)

# --------------------------------------------------------------------------- #
# Run calculation
# --------------------------------------------------------------------------- #
if run_clicked:
    if not live_file or not sold_file:
        st.warning("Please upload both Live_Data and Sold_Data files.")
        st.stop()

    with st.spinner("Calculating ATP... this can take a few seconds for large files."):
        try:
            response = requests.post(
                f"{API}/calculate",
                files={
                    "live_file": (live_file.name, live_file.getvalue()),
                    "sold_file": (sold_file.name, sold_file.getvalue()),
                },
                data={
                    "tolerance_pct": tolerance_pct,
                    "bullion_categories": bullion_categories,
                    "tail_badges": tail_badges,
                    "generate_seller_zip": generate_seller_zip,
                    "generate_seller_tail_zip": generate_seller_tail_zip,
                },
                timeout=300,
            )
        except requests.RequestException as exc:
            st.error(f"Request to backend failed: {exc}")
            st.stop()

    if response.status_code != 200:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        st.error(f"Calculation failed: {detail}")
        st.stop()

    st.session_state["atp_result"] = response.json()

# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #
result = st.session_state.get("atp_result")
if result:
    meta = result["meta"]

    st.divider()
    st.subheader("Results")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Sellers", meta["unique_sellers"])
    m2.metric("Unique sold DKPCs", meta["sold_dkpc_unique"])
    m3.metric("Unique sold DKPs", meta["sold_dkp_unique"])
    m4.metric("Calculated in", f"{meta['execution_seconds']}s")

    summary_df = pd.DataFrame(result["summary"]).rename(
        columns={
            "seller_id": "Seller ID",
            "seller": "Seller",
            "dkpc_atp_pct_bullion": "DKPC ATP % (Bullion)",
            "dkp_atp_pct_bullion": "DKP ATP % (Bullion)",
            "dkpc_atp_pct_jewelry": "DKPC ATP % (Jewelry)",
            "dkp_atp_pct_jewelry": "DKP ATP % (Jewelry)",
        }
    )
    pct_columns = [
        "DKPC ATP % (Bullion)", "DKP ATP % (Bullion)",
        "DKPC ATP % (Jewelry)", "DKP ATP % (Jewelry)",
    ]

    tab_summary, tab_missing, tab_tail, tab_seller_tail = st.tabs(
        ["📊 Summary", "🔻 Seller ATP DKPC", "🎯 Category ST/MT/LT PER Seller", "📮 Per-Seller Item-Tail"]
    )

    with tab_summary:
        styled_summary = summary_df.style.format({c: "{:.2f}%" for c in pct_columns})
        if _MATPLOTLIB_AVAILABLE:
            styled_summary = styled_summary.background_gradient(subset=pct_columns, cmap="RdYlGn", vmin=0, vmax=100)
        else:
            st.caption("Install matplotlib to enable colored cell shading in this table.")
        st.dataframe(
            styled_summary,
            use_container_width=True,
            hide_index=True,
        )
        dl_summary = requests.get(f"{API}/download/summary/{result['result_id']}", timeout=60)
        st.download_button(
            "⬇ Download Summary.xlsx",
            data=dl_summary.content,
            file_name="Summary.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    with tab_missing:
        st.caption(
            "Same per-seller ST/MT/LT ranking and item selection as the **Per-Seller Item-Tail** "
            "tab, but one row per **DKPC** (product variant) instead of per DKP — so availability "
            "is the weight-aware DKPC-level result — and every row shows whether it is still "
            "**Available** or has gone **Unavailable**. Within each seller, Unavailable rows come "
            "first, then ST → MT → LT."
        )
        missing_preview_df = pd.DataFrame(result["missing_preview"]).rename(
            columns={
                "seller_id": "Seller ID", "seller": "Seller", "dkp": "DKP",
                "dkp_name": "DKP Name", "dkpc": "DKPC", "category": "Category",
                "bucket": "Bucket", "tail_badge": "Tail Badge", "status": "Status",
            }
        )
        total = result["missing_total_count"]
        unavailable = result.get("missing_unavailable_count", 0)
        if total == 0:
            st.info(
                "No sold DKPC has a resolvable Item-Tail badge (sum_net_item_fcast is zero/blank "
                "for all of them)."
            )
        else:
            shown = len(missing_preview_df)
            st.caption(
                f"{total} badged DKPC row(s) — {unavailable} unavailable, {total - unavailable} available."
                + (
                    f" Showing the first {shown}; download the file for the complete list."
                    if shown < total else ""
                )
            )
            st.dataframe(missing_preview_df, use_container_width=True, hide_index=True)

        dl_missing = requests.get(f"{API}/download/missing/{result['result_id']}", timeout=60)
        st.download_button(
            "⬇ Download ATP_Missing.xlsx",
            data=dl_missing.content,
            file_name="ATP_Missing.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

        if meta.get("seller_zip_generated"):
            st.divider()
            st.caption(
                "📮 Per-seller ZIP — the **Unavailable** rows of this table only (the actionable "
                "\"make these live again\" hand-off), one xlsx per seller, plus each row's weight."
            )
            dl_zip = requests.get(f"{API}/download/seller-zip/{result['result_id']}", timeout=60)
            st.download_button(
                "⬇ Download per-seller ZIP (ATP_Missing_by_Seller.zip)",
                data=dl_zip.content,
                file_name="ATP_Missing_by_Seller.zip",
                mime="application/zip",
                use_container_width=True,
            )

    with tab_tail:
        tail_summary_df = pd.DataFrame(result["tail_summary"]).rename(
            columns={
                "seller_id": "Seller ID", "seller": "Seller",
                "st_available": "ST Available", "st_unavailable": "ST Unavailable",
                "mt_available": "MT Available", "mt_unavailable": "MT Unavailable",
                "lt_available": "LT Available", "lt_unavailable": "LT Unavailable",
            }
        )
        tail_count_columns = [
            "ST Available", "ST Unavailable", "MT Available", "MT Unavailable",
            "LT Available", "LT Unavailable",
        ]
        if tail_summary_df.empty:
            st.info("No sold DKP has a resolvable Item-Tail badge (sum_net_item_fcast is zero/blank for all).")
        else:
            st.caption("📋 Overall table — DKP counts per seller, per Item-Tail badge, split by ATP status (weight-independent, DKP-level).")
            styled_tail_summary = tail_summary_df.style
            if _MATPLOTLIB_AVAILABLE:
                styled_tail_summary = styled_tail_summary.background_gradient(
                    subset=tail_count_columns, cmap="RdYlGn"
                )
            else:
                st.caption("Install matplotlib to enable colored cell shading in this table.")
            st.dataframe(styled_tail_summary, use_container_width=True, hide_index=True)
            dl_tail_summary = requests.get(f"{API}/download/tail-summary/{result['result_id']}", timeout=60)
            st.download_button(
                "⬇ Download Tail_Summary.xlsx (overall table)",
                data=dl_tail_summary.content,
                file_name="Tail_Summary.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

            st.divider()
            st.caption("📦 Item list — every badged DKP across all sellers, in one flat file (not split per seller).")
            dl_tail_dkp_list = requests.get(f"{API}/download/tail-dkp-list/{result['result_id']}", timeout=60)
            st.download_button(
                "⬇ Download Tail_DKP_List.xlsx (item list)",
                data=dl_tail_dkp_list.content,
                file_name="Tail_DKP_List.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

    with tab_seller_tail:
        st.caption(
            "Same ST/MT/LT rule as the tab above, but ranked separately for **each seller's own** "
            "sold volume instead of marketplace-wide — a seller's own top 30% is ST regardless of "
            "how it compares to other sellers."
        )
        seller_tail_summary_df = pd.DataFrame(result["seller_tail_summary"]).rename(
            columns={
                "seller_id": "Seller ID", "seller": "Seller",
                "st_available": "ST Available", "st_unavailable": "ST Unavailable",
                "mt_available": "MT Available", "mt_unavailable": "MT Unavailable",
                "lt_available": "LT Available", "lt_unavailable": "LT Unavailable",
            }
        )
        if seller_tail_summary_df.empty:
            st.info("No sold DKP has a resolvable Item-Tail badge (sum_net_item_fcast is zero/blank for all).")
        else:
            st.caption("📋 Overall table — DKP counts per seller, per own-ranked Item-Tail badge, split by ATP status.")
            styled_seller_tail_summary = seller_tail_summary_df.style
            if _MATPLOTLIB_AVAILABLE:
                styled_seller_tail_summary = styled_seller_tail_summary.background_gradient(
                    subset=tail_count_columns, cmap="RdYlGn"
                )
            else:
                st.caption("Install matplotlib to enable colored cell shading in this table.")
            st.dataframe(styled_seller_tail_summary, use_container_width=True, hide_index=True)
            dl_seller_tail_summary = requests.get(
                f"{API}/download/seller-tail-summary/{result['result_id']}", timeout=60
            )
            st.download_button(
                "⬇ Download Seller_Tail_Summary.xlsx (overall table)",
                data=dl_seller_tail_summary.content,
                file_name="Seller_Tail_Summary.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

            st.divider()
            st.caption("📦 Item list — every badged DKP across all sellers, in one flat file (not split per seller).")
            dl_seller_tail_dkp_list = requests.get(
                f"{API}/download/seller-tail-dkp-list/{result['result_id']}", timeout=60
            )
            st.download_button(
                "⬇ Download Seller_Tail_DKP_List.xlsx (item list)",
                data=dl_seller_tail_dkp_list.content,
                file_name="Seller_Tail_DKP_List.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

            if meta.get("seller_tail_zip_generated"):
                st.divider()
                st.caption("📮 Per-seller ZIP — same badged DKPs, split into one xlsx per seller (SellerID-SellerName.xlsx).")
                dl_seller_tail_zip = requests.get(
                    f"{API}/download/seller-tail-zip/{result['result_id']}", timeout=60
                )
                st.download_button(
                    "⬇ Download Seller_Tail_DKP_List_by_Seller.zip (per-seller)",
                    data=dl_seller_tail_zip.content,
                    file_name="Seller_Tail_DKP_List_by_Seller.zip",
                    mime="application/zip",
                    use_container_width=True,
                )

    if meta["warnings"]:
        with st.expander(f"⚠️ {len(meta['warnings'])} data warning(s)"):
            for w in meta["warnings"]:
                st.write(f"- {w}")

# --------------------------------------------------------------------------- #
# Footer — rendered outside the results block so it's always visible, even
# before the first calculation.
# --------------------------------------------------------------------------- #
st.markdown(
    f"""
    <div class="atp-footer">
        Built by <strong>Haj Mehdi</strong> — questions, bugs, or feature ideas? Get in touch.
        <div class="atp-footer-links">
            <a href="{GITHUB_URL}" target="_blank" rel="noopener noreferrer">🐙 GitHub</a>
            <a href="{TELEGRAM_URL}" target="_blank" rel="noopener noreferrer">✈️ Telegram {TELEGRAM_HANDLE}</a>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
