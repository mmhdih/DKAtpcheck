"""
missing_generator.py
----------------------
Builds the "Seller ATP DKPC" table: the DKPC-level counterpart of the
Per-Seller Item-Tail report.

Items are identified exactly the way that report identifies them — one
row per unique sold item whose DKP carries an Item-Tail badge from the
seller's OWN ranking (so a DKP with a zero/blank sum_net_item_fcast, and
therefore no badge, is excluded here too) — with two differences:

  1. The row is a DKPC (product_variant_id), not a DKP, so availability is
     the weight-aware DKPC-level ATP outcome rather than the
     weight-independent DKP-level one.
  2. Every row carries its Available/Unavailable status, so the table
     shows what is still live next to what has gone missing, instead of
     listing the missing rows alone.

The caller decides which badge the `tail_badge` column holds; app.py
passes the per-seller-ranked one, matching the Per-Seller Item-Tail tab
this report mirrors.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .atp_engine import ATPResult
from .config import CanonicalColumns as C
from .config import TailClassification
from .report_labels import (
    STATUS_AVAILABLE,
    STATUS_COLORS,
    STATUS_COLUMN,
    STATUS_UNAVAILABLE,
    TAIL_BADGE_COLORS,
    TAIL_BADGE_COLUMN,
    TAIL_BADGE_SORT_RANK,
)
from .utils import dataframe_to_excel_bytes, get_logger

logger = get_logger(__name__)

SELLER_ID_COLUMN = "Seller ID"
SELLER_COLUMN = "Seller"
DKP_COLUMN = "DKP"
DKP_NAME_COLUMN = "DKP Name"
DKPC_COLUMN = "DKPC"
CATEGORY_COLUMN = "Category"
BUCKET_COLUMN = "Bucket"

OUTPUT_COLUMNS = [
    SELLER_ID_COLUMN, SELLER_COLUMN, DKP_COLUMN, DKP_NAME_COLUMN, DKPC_COLUMN,
    CATEGORY_COLUMN, BUCKET_COLUMN, TAIL_BADGE_COLUMN, STATUS_COLUMN,
]


def build_missing(result: ATPResult) -> pd.DataFrame:
    """
    Returns a DataFrame with columns: Seller ID, Seller, DKP, DKP Name,
    DKPC, Category, Bucket, Tail Badge, Status.

    One row per unique sold DKPC whose DKP is badged, sorted per seller
    with the actionable rows first: Unavailable before Available, then
    ST -> MT -> LT, then by DKPC.
    """
    df = result.dkpc_results
    badged = df[df[C.TAIL_BADGE].isin(TailClassification.ALL)]
    if badged.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    listing = pd.DataFrame(
        {
            SELLER_ID_COLUMN: badged[C.SELLER_ID],
            SELLER_COLUMN: badged[C.SELLER],
            DKP_COLUMN: badged[C.DKP],
            DKP_NAME_COLUMN: badged[C.DKP_NAME],
            DKPC_COLUMN: badged[C.DKPC],
            CATEGORY_COLUMN: badged[C.CATEGORY],
            BUCKET_COLUMN: badged[C.BUCKET],
            TAIL_BADGE_COLUMN: badged[C.TAIL_BADGE],
            STATUS_COLUMN: np.where(badged["is_atp"], STATUS_AVAILABLE, STATUS_UNAVAILABLE),
        }
    )
    listing = listing.assign(
        _seller_sort=listing[SELLER_COLUMN].astype(str).str.casefold(),
        _status_sort=(listing[STATUS_COLUMN] == STATUS_AVAILABLE).astype(int),
        _badge_sort=listing[TAIL_BADGE_COLUMN].map(TAIL_BADGE_SORT_RANK),
        _dkpc_sort=listing[DKPC_COLUMN].astype(str).str.casefold(),
    )
    listing = (
        listing.sort_values(
            ["_seller_sort", "_status_sort", "_badge_sort", "_dkpc_sort"], kind="stable"
        )
        .drop(columns=["_seller_sort", "_status_sort", "_badge_sort", "_dkpc_sort"])
        .reset_index(drop=True)
    )

    unavailable = int((listing[STATUS_COLUMN] == STATUS_UNAVAILABLE).sum())
    logger.info(
        "Built Seller ATP DKPC with %d badged DKPC row(s) (%d unavailable).",
        len(listing), unavailable,
    )
    return listing


def missing_to_excel_bytes(missing_df: pd.DataFrame) -> bytes:
    return dataframe_to_excel_bytes(
        missing_df,
        sheet_name="ATP_Missing",
        categorical_color_columns={
            TAIL_BADGE_COLUMN: TAIL_BADGE_COLORS,
            STATUS_COLUMN: STATUS_COLORS,
        },
    )
