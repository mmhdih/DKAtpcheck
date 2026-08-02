"""
summary_generator.py
---------------------
Builds the Summary table: one row per seller, showing the percentage of
their SOLD DKPCs/DKPs that are ATP, split into Bullion vs Jewelry category
buckets. Percentages only — no counts — per the spec, computed over unique
DKPC/DKP pairs (matching ATPEngine's deduplication).
"""
from __future__ import annotations

import pandas as pd

from .atp_engine import ATPResult
from .config import CanonicalColumns as C
from .config import CategoryBucket
from .utils import dataframe_to_excel_bytes, get_logger

logger = get_logger(__name__)

SELLER_ID_COLUMN = "Seller ID"
SELLER_COLUMN = "Seller"
DKPC_PCT_BULLION_COLUMN = "DKPC ATP % (Bullion)"
DKP_PCT_BULLION_COLUMN = "DKP ATP % (Bullion)"
DKPC_PCT_JEWELRY_COLUMN = "DKPC ATP % (Jewelry)"
DKP_PCT_JEWELRY_COLUMN = "DKP ATP % (Jewelry)"

_PCT_COLUMNS = (
    DKPC_PCT_BULLION_COLUMN, DKP_PCT_BULLION_COLUMN,
    DKPC_PCT_JEWELRY_COLUMN, DKP_PCT_JEWELRY_COLUMN,
)


def _pct_by_seller(df: pd.DataFrame) -> pd.Series:
    """seller_key -> ATP percentage (0-100), rounded to 2 decimals."""
    return (df.groupby(C.SELLER_KEY)["is_atp"].mean() * 100).round(2)


def _pct_by_seller_for_bucket(df: pd.DataFrame, bucket: str) -> pd.Series:
    return _pct_by_seller(df[df[C.BUCKET] == bucket])


def _display_name_by_seller(df: pd.DataFrame) -> pd.Series:
    """seller_key -> the first-seen display name (original casing) for that seller."""
    return df.drop_duplicates(subset=[C.SELLER_KEY]).set_index(C.SELLER_KEY)[C.SELLER]


def _seller_id_by_seller(df: pd.DataFrame) -> pd.Series:
    """seller_key -> seller_id (identical for every row in the group, by construction)."""
    return df.drop_duplicates(subset=[C.SELLER_KEY]).set_index(C.SELLER_KEY)[C.SELLER_ID]


def build_summary(result: ATPResult) -> pd.DataFrame:
    """
    Returns a DataFrame with columns: Seller ID, Seller,
    DKPC ATP % (Bullion), DKP ATP % (Bullion),
    DKPC ATP % (Jewelry), DKP ATP % (Jewelry)
    sorted alphabetically by Seller.
    """
    dkpc_bullion = _pct_by_seller_for_bucket(result.dkpc_results, CategoryBucket.BULLION)
    dkp_bullion = _pct_by_seller_for_bucket(result.dkp_results, CategoryBucket.BULLION)
    dkpc_jewelry = _pct_by_seller_for_bucket(result.dkpc_results, CategoryBucket.JEWELRY)
    dkp_jewelry = _pct_by_seller_for_bucket(result.dkp_results, CategoryBucket.JEWELRY)

    # A seller might (in theory) have sold DKPCs but the corresponding DKP
    # rows deduplicated differently; union the seller_key index from both
    # sides so no seller silently disappears.
    combined = pd.concat(
        [
            result.dkpc_results[[C.SELLER_KEY, C.SELLER, C.SELLER_ID]],
            result.dkp_results[[C.SELLER_KEY, C.SELLER, C.SELLER_ID]],
        ]
    )
    display_names = _display_name_by_seller(combined)
    seller_ids = _seller_id_by_seller(combined)

    summary = pd.DataFrame(
        {
            DKPC_PCT_BULLION_COLUMN: dkpc_bullion,
            DKP_PCT_BULLION_COLUMN: dkp_bullion,
            DKPC_PCT_JEWELRY_COLUMN: dkpc_jewelry,
            DKP_PCT_JEWELRY_COLUMN: dkp_jewelry,
        }
    )
    summary[SELLER_COLUMN] = display_names.reindex(summary.index)
    summary[SELLER_ID_COLUMN] = seller_ids.reindex(summary.index)
    summary = summary.reset_index(drop=True)[[SELLER_ID_COLUMN, SELLER_COLUMN, *_PCT_COLUMNS]]
    summary[list(_PCT_COLUMNS)] = summary[list(_PCT_COLUMNS)].fillna(0.0)
    summary = summary.sort_values(
        SELLER_COLUMN, key=lambda s: s.str.casefold(), kind="stable"
    ).reset_index(drop=True)

    logger.info("Built summary for %d sellers.", len(summary))
    return summary


def summary_to_excel_bytes(summary_df: pd.DataFrame) -> bytes:
    return dataframe_to_excel_bytes(
        summary_df,
        sheet_name="Summary",
        percent_columns=_PCT_COLUMNS,
        color_scale_columns=_PCT_COLUMNS,
    )
