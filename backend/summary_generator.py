"""
summary_generator.py
---------------------
Builds the Summary table: one row per seller, showing the percentage of
their SOLD DKPCs/DKPs that are ATP. Percentages only — no counts — per
the spec, computed over unique DKPC/DKP pairs (matching ATPEngine's
deduplication).
"""
from __future__ import annotations

import pandas as pd

from .atp_engine import ATPResult
from .config import CanonicalColumns as C
from .utils import dataframe_to_excel_bytes, get_logger

logger = get_logger(__name__)

SELLER_COLUMN = "Seller"
DKPC_PCT_COLUMN = "DKPC ATP %"
DKP_PCT_COLUMN = "DKP ATP %"


def _pct_by_seller(df: pd.DataFrame) -> pd.Series:
    """seller_key -> ATP percentage (0-100), rounded to 2 decimals."""
    return (df.groupby(C.SELLER_KEY)["is_atp"].mean() * 100).round(2)


def _display_name_by_seller(df: pd.DataFrame) -> pd.Series:
    """seller_key -> the first-seen display name (original casing) for that seller."""
    return df.drop_duplicates(subset=[C.SELLER_KEY]).set_index(C.SELLER_KEY)[C.SELLER]


def build_summary(result: ATPResult) -> pd.DataFrame:
    """
    Returns a DataFrame with columns: Seller, DKPC ATP %, DKP ATP %
    sorted alphabetically by Seller.
    """
    dkpc_pct = _pct_by_seller(result.dkpc_results)
    dkp_pct = _pct_by_seller(result.dkp_results)

    # A seller might (in theory) have sold DKPCs but the corresponding DKP
    # rows deduplicated differently; union the seller_key index from both
    # sides so no seller silently disappears.
    display_names = _display_name_by_seller(
        pd.concat([result.dkpc_results[[C.SELLER_KEY, C.SELLER]], result.dkp_results[[C.SELLER_KEY, C.SELLER]]])
    )

    summary = pd.DataFrame(
        {
            DKPC_PCT_COLUMN: dkpc_pct,
            DKP_PCT_COLUMN: dkp_pct,
        }
    )
    summary[SELLER_COLUMN] = display_names.reindex(summary.index)
    summary = summary.reset_index(drop=True)[[SELLER_COLUMN, DKPC_PCT_COLUMN, DKP_PCT_COLUMN]]
    summary = summary.fillna(0.0).sort_values(
        SELLER_COLUMN, key=lambda s: s.str.casefold(), kind="stable"
    ).reset_index(drop=True)

    logger.info("Built summary for %d sellers.", len(summary))
    return summary


def summary_to_excel_bytes(summary_df: pd.DataFrame) -> bytes:
    return dataframe_to_excel_bytes(
        summary_df,
        sheet_name="Summary",
        percent_columns=(DKPC_PCT_COLUMN, DKP_PCT_COLUMN),
    )
