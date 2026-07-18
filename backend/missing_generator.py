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

SELLER_COLUMN = "Seller"
DKP_COLUMN = "DKP"
DKPC_COLUMN = "DKPC"


def build_missing(result: ATPResult) -> pd.DataFrame:
    """Returns a DataFrame with columns: Seller, DKP, DKPC — sorted by Seller then DKPC."""
    missing = result.dkpc_results.loc[~result.dkpc_results["is_atp"], [C.SELLER, C.DKP, C.DKPC]].copy()
    missing.columns = [SELLER_COLUMN, DKP_COLUMN, DKPC_COLUMN]
    missing = missing.sort_values(
        [SELLER_COLUMN, DKPC_COLUMN], key=lambda s: s.str.casefold(), kind="stable"
    ).reset_index(drop=True)

    logger.info("Built ATP_Missing with %d row(s).", len(missing))
    return missing


def missing_to_excel_bytes(missing_df: pd.DataFrame) -> bytes:
    return dataframe_to_excel_bytes(missing_df, sheet_name="ATP_Missing")
