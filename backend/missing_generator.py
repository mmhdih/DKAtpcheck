"""
missing_generator.py
----------------------
Builds the ATP_Missing table: every unique SOLD DKPC that is NOT ATP,
so it can be sent to sellers as an actionable "make these live again" list.
"""
from __future__ import annotations

import pandas as pd

from .atp_engine import ATPResult
from .config import CanonicalColumns as C
from .utils import dataframe_to_excel_bytes, get_logger

logger = get_logger(__name__)

SELLER_ID_COLUMN = "Seller ID"
SELLER_COLUMN = "Seller"
DKP_COLUMN = "DKP"
DKPC_COLUMN = "DKPC"
CATEGORY_COLUMN = "Category"
BUCKET_COLUMN = "Bucket"

_COLUMN_RENAME = {
    C.SELLER_ID: SELLER_ID_COLUMN,
    C.SELLER: SELLER_COLUMN,
    C.DKP: DKP_COLUMN,
    C.DKPC: DKPC_COLUMN,
    C.CATEGORY: CATEGORY_COLUMN,
    C.BUCKET: BUCKET_COLUMN,
}


def build_missing(result: ATPResult) -> pd.DataFrame:
    """Returns a DataFrame with columns: Seller ID, Seller, DKP, DKPC, Category, Bucket."""
    cols = [C.SELLER_ID, C.SELLER, C.DKP, C.DKPC, C.CATEGORY, C.BUCKET]
    missing = result.dkpc_results.loc[~result.dkpc_results["is_atp"], cols].copy()
    missing = missing.rename(columns=_COLUMN_RENAME)
    missing = missing.sort_values(
        [SELLER_COLUMN, DKPC_COLUMN], key=lambda s: s.str.casefold(), kind="stable"
    ).reset_index(drop=True)

    logger.info("Built ATP_Missing with %d row(s).", len(missing))
    return missing


def missing_to_excel_bytes(missing_df: pd.DataFrame) -> bytes:
    return dataframe_to_excel_bytes(missing_df, sheet_name="ATP_Missing")
