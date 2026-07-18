"""
streamlit_app.py
------------------
Thin UI client for the ATP Analyzer FastAPI backend. Contains no business
logic: it uploads the two Excel files, lets the user set the weight
tolerance, calls the backend, and renders the Summary / ATP_Missing
results with download buttons.

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

BACKEND_URL = os.environ.get("ATP_BACKEND_URL", "http://localhost:8000").rstrip("/")
API = f"{BACKEND_URL}/api/v1"

st.set_page_config(page_title="ATP Analyzer", page_icon="📦", layout="wide")

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
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

st.markdown(
    """
    <div class="atp-hero">
        <h1>📦 ATP Analyzer</h1>
        <p>Upload Live_Data and Sold_Data to find out which sold products are Available To Purchase.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=60, show_spinner=False)
def _fetch_backend_config() -> dict:
    resp = requests.get(f"{API}/config", timeout=10)
    resp.raise_for_status()
    return resp.json()


try:
    backend_cfg = _fetch_backend_config()
except requests.RequestException:
    st.error(
        f"Can't reach the ATP Analyzer backend at `{BACKEND_URL}`. "
        "Make sure it's running (`uvicorn backend.app:app`)."
    )
    st.stop()

# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #
col_left, col_right = st.columns(2, gap="large")

with col_left:
    st.markdown('<div class="atp-card">', unsafe_allow_html=True)
    st.subheader("1. Upload files")
    live_file = st.file_uploader("Live_Data.xlsx", type=["xlsx"], key="live_file")
    sold_file = st.file_uploader("Sold_Data.xlsx", type=["xlsx"], key="sold_file")
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
        st.caption(f"Using {tolerance_pct}% tolerance. A sold DKPC matches if a live item of the same seller falls within ±{tolerance_pct}% of its weight.")
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
                data={"tolerance_pct": tolerance_pct},
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
        columns={"seller": "Seller", "dkpc_atp_pct": "DKPC ATP %", "dkp_atp_pct": "DKP ATP %"}
    )

    tab_summary, tab_missing = st.tabs(["📊 Summary", "🔻 ATP Missing"])

    with tab_summary:
        st.dataframe(
            summary_df.style.format({"DKPC ATP %": "{:.2f}%", "DKP ATP %": "{:.2f}%"})
            .background_gradient(subset=["DKPC ATP %", "DKP ATP %"], cmap="RdYlGn", vmin=0, vmax=100),
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
        missing_preview_df = pd.DataFrame(result["missing_preview"]).rename(
            columns={"seller": "Seller", "dkp": "DKP", "dkpc": "DKPC"}
        )
        total = result["missing_total_count"]
        if total == 0:
            st.success("Every sold DKPC is ATP. Nothing to report.")
        else:
            shown = len(missing_preview_df)
            st.caption(
                f"Showing {shown} of {total} row(s). Download the file for the complete list."
                if shown < total else f"Showing all {total} row(s)."
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

    if meta["warnings"]:
        with st.expander(f"⚠️ {len(meta['warnings'])} data warning(s)"):
            for w in meta["warnings"]:
                st.write(f"- {w}")
