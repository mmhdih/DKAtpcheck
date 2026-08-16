"""
tail_summary_generator.py
---------------------------
Builds the two outputs behind the "Category ST/MT/LT per Seller" tab:

  1. build_tail_summary: an aggregated table — for each seller, how many
     of their sold DKPs in each Item-Tail bucket (ST/MT/LT) are currently
     ATP (available) vs NOT ATP (unavailable).
  2. build_tail_dkp_list: a flat, single-sheet list of every badged DKP
     across every seller (no per-seller split), for a "give me the raw
     item list" download.

Both are computed at the DKP level — the Item-Tail badge is itself a
DKP-level concept (all DKPCs under one DKP share the same badge), so
DKP-level ATP (weight-independent) is the natural status to report here.
DKPs with no badge at all (zero/blank sum_net_item_fcast) are excluded
from both, consistent with how they're excluded from ranking.

A third output, build_tail_dkp_zip, re-splits build_tail_dkp_list's flat
listing per seller — one styled .xlsx per Seller ID, named
"<SellerID>-<SellerName>.xlsx" (same convention as seller_export.py's
NOT-ATP ZIP) — for teams that want the ST/MT/LT breakdown as a standalone
per-seller hand-off file instead of one combined sheet.
"""
from __future__ import annotations

import io
import zipfile

import numpy as np
import pandas as pd

from .atp_engine import ATPResult
from .config import CanonicalColumns as C
from .config import TailClassification
from .utils import dataframe_to_excel_bytes, get_logger, safe_filename_part

logger = get_logger(__name__)

SELLER_ID_COLUMN = "Seller ID"
SELLER_COLUMN = "Seller"
DKP_COLUMN = "DKP"
CATEGORY_COLUMN = "Category"
BUCKET_COLUMN = "Bucket"
TAIL_BADGE_COLUMN = "Tail Badge"
STATUS_COLUMN = "Status"
STATUS_AVAILABLE = "Available"
STATUS_UNAVAILABLE = "Unavailable"

# Categorical cell-fill colors for the DKP-list export, matching the same
# red/yellow/green visual language as the on-screen/exported color scales.
_TAIL_BADGE_COLORS = {
    TailClassification.ST: "63BE7B",  # green
    TailClassification.MT: "FFEB84",  # yellow
    TailClassification.LT: "F8696B",  # red
}
_STATUS_COLORS = {
    STATUS_AVAILABLE: "63BE7B",  # green
    STATUS_UNAVAILABLE: "F8696B",  # red
}


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
    return dataframe_to_excel_bytes(
        tail_summary_df,
        sheet_name="Tail_Summary",
        color_scale_columns=_COUNT_COLUMNS,
    )


def build_tail_dkp_list(result: ATPResult) -> pd.DataFrame:
    """
    Returns a flat DataFrame — one row per badged DKP across ALL sellers
    combined (no per-seller split): Seller ID, Seller, DKP, Category,
    Bucket, Tail Badge, Status (Available/Unavailable). Sorted by Seller
    then DKP.
    """
    df = result.dkp_results
    badged = df[df[C.TAIL_BADGE].isin(TailClassification.ALL)]
    if badged.empty:
        return pd.DataFrame(
            columns=[
                SELLER_ID_COLUMN, SELLER_COLUMN, DKP_COLUMN,
                CATEGORY_COLUMN, BUCKET_COLUMN, TAIL_BADGE_COLUMN, STATUS_COLUMN,
            ]
        )

    listing = pd.DataFrame(
        {
            SELLER_ID_COLUMN: badged[C.SELLER_ID],
            SELLER_COLUMN: badged[C.SELLER],
            DKP_COLUMN: badged[C.DKP],
            CATEGORY_COLUMN: badged[C.CATEGORY],
            BUCKET_COLUMN: badged[C.BUCKET],
            TAIL_BADGE_COLUMN: badged[C.TAIL_BADGE],
            STATUS_COLUMN: np.where(badged["is_atp"], STATUS_AVAILABLE, STATUS_UNAVAILABLE),
        }
    )
    listing = listing.sort_values(
        [SELLER_COLUMN, DKP_COLUMN],
        key=lambda s: s.astype(str).str.casefold(),
        kind="stable",
    ).reset_index(drop=True)

    logger.info("Built tail DKP list with %d row(s).", len(listing))
    return listing


def tail_dkp_list_to_excel_bytes(tail_dkp_list_df: pd.DataFrame) -> bytes:
    return dataframe_to_excel_bytes(
        tail_dkp_list_df,
        sheet_name="Tail_DKP_List",
        categorical_color_columns={
            TAIL_BADGE_COLUMN: _TAIL_BADGE_COLORS,
            STATUS_COLUMN: _STATUS_COLORS,
        },
    )


def build_tail_dkp_zip(result: ATPResult) -> bytes:
    """
    Same badged-DKP rows as build_tail_dkp_list, but split into one styled
    .xlsx per Seller ID instead of a single combined sheet.

    Returns:
        Raw .zip bytes containing one "<SellerID>-<SellerName>.xlsx" per
        seller with at least one badged DKP, each sheet listing that
        seller's Seller ID, Seller, DKP, Category, Bucket, Tail Badge and
        Status (Available/Unavailable) rows, sorted by DKP. Sellers with
        no badged DKPs at all (same exclusion rule as build_tail_dkp_list)
        get no file.
    """
    listing = build_tail_dkp_list(result)

    buffer = io.BytesIO()
    seller_count = 0
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for seller_id, group in listing.groupby(SELLER_ID_COLUMN, sort=True):
            seller_name = group[SELLER_COLUMN].iloc[0] if len(group) else ""
            xlsx_bytes = dataframe_to_excel_bytes(
                group.reset_index(drop=True),
                sheet_name="Tail_DKP_List",
                categorical_color_columns={
                    TAIL_BADGE_COLUMN: _TAIL_BADGE_COLORS,
                    STATUS_COLUMN: _STATUS_COLORS,
                },
            )
            filename = f"{safe_filename_part(seller_id)}-{safe_filename_part(seller_name)}.xlsx"
            zf.writestr(filename, xlsx_bytes)
            seller_count += 1

    logger.info("Built per-seller Tail_DKP_List ZIP export for %d seller(s).", seller_count)
    buffer.seek(0)
    return buffer.read()
