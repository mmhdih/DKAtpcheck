"""
tail_summary_generator.py
---------------------------
Builds the Tail Summary table: for each seller, how many of their sold
DKPs in each Item-Tail bucket (ST/MT/LT) are currently ATP (available) vs
NOT ATP (unavailable). Computed at the DKP level — the Item-Tail badge is
itself a DKP-level concept (all DKPCs under one DKP share the same
badge), so DKP-level ATP (weight-independent) is the natural status to
report here. DKPs with no badge at all (zero/blank sum_net_item_fcast)
are excluded, consistent with how they're excluded from ranking.
"""
from __future__ import annotations

import pandas as pd

from .atp_engine import ATPResult
from .config import CanonicalColumns as C
from .config import TailClassification
from .utils import dataframe_to_excel_bytes, get_logger

logger = get_logger(__name__)

SELLER_ID_COLUMN = "Seller ID"
SELLER_COLUMN = "Seller"


def _count_columns(badge: str) -> tuple[str, str]:
    return f"{badge} Available", f"{badge} Unavailable"


_COUNT_COLUMNS = tuple(col for badge in TailClassification.ALL for col in _count_columns(badge))


def _count_by_seller(df: pd.DataFrame, badge: str, is_atp: bool) -> pd.Series:
    subset = df[(df[C.TAIL_BADGE] == badge) & (df["is_atp"] == is_atp)]
    return subset.groupby(C.SELLER_KEY).size()


def build_tail_summary(result: ATPResult) -> pd.DataFrame:
    """
    Returns a DataFrame with columns: Seller ID, Seller, then for each of
    ST/MT/LT: "<badge> Available" and "<badge> Unavailable" (DKP counts).
    Sellers with no badged DKPs at all are omitted. Sorted alphabetically
    by Seller.
    """
    df = result.dkp_results

    counts = {}
    for badge in TailClassification.ALL:
        available_col, unavailable_col = _count_columns(badge)
        counts[available_col] = _count_by_seller(df, badge, True)
        counts[unavailable_col] = _count_by_seller(df, badge, False)

    tail_summary = pd.DataFrame(counts)
    if tail_summary.empty:
        return pd.DataFrame(columns=[SELLER_ID_COLUMN, SELLER_COLUMN, *_COUNT_COLUMNS])

    display_names = df.drop_duplicates(subset=[C.SELLER_KEY]).set_index(C.SELLER_KEY)[C.SELLER]
    seller_ids = df.drop_duplicates(subset=[C.SELLER_KEY]).set_index(C.SELLER_KEY)[C.SELLER_ID]

    tail_summary[SELLER_COLUMN] = display_names.reindex(tail_summary.index)
    tail_summary[SELLER_ID_COLUMN] = seller_ids.reindex(tail_summary.index)
    tail_summary[list(_COUNT_COLUMNS)] = tail_summary[list(_COUNT_COLUMNS)].fillna(0).astype(int)
    tail_summary = tail_summary.reset_index(drop=True)[[SELLER_ID_COLUMN, SELLER_COLUMN, *_COUNT_COLUMNS]]
    tail_summary = tail_summary.sort_values(
        SELLER_COLUMN, key=lambda s: s.str.casefold(), kind="stable"
    ).reset_index(drop=True)

    logger.info("Built tail summary for %d seller(s).", len(tail_summary))
    return tail_summary


def tail_summary_to_excel_bytes(tail_summary_df: pd.DataFrame) -> bytes:
    return dataframe_to_excel_bytes(tail_summary_df, sheet_name="Tail_Summary")
