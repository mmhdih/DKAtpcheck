"""
seller_export.py
-----------------
Builds a ZIP of one styled .xlsx per Seller ID, listing that seller's
NOT-ATP sold DKPCs — an actionable per-seller hand-off list, richer than
the on-screen ATP_Missing table (adds Weight, Category, Bucket, Tail
Badge; the raw net_item_fcast number is used only to pre-sort rows and is
never written to the output). Rows with a zero/blank net_item_fcast are
excluded entirely, not merely sorted last.

Reuses utils.dataframe_to_excel_bytes for the actual xlsx styling.
"""
from __future__ import annotations

import io
import re
import zipfile

import pandas as pd

from .atp_engine import ATPResult
from .config import CanonicalColumns as C
from .utils import dataframe_to_excel_bytes, get_logger

logger = get_logger(__name__)

SELLER_ID_COLUMN = "Seller ID"
SELLER_COLUMN = "Seller"
DKP_COLUMN = "DKP"
DKPC_COLUMN = "DKPC"
WEIGHT_COLUMN = "Weight"
CATEGORY_COLUMN = "Category"
BUCKET_COLUMN = "Bucket"
TAIL_BADGE_COLUMN = "Tail Badge"

_FILENAME_SANITIZE_RE = re.compile(r"[^A-Za-z0-9_-]+")


def _safe_filename_part(value: str) -> str:
    return _FILENAME_SANITIZE_RE.sub("_", str(value)).strip("_") or "unknown"


def build_seller_missing_zip(result: ATPResult) -> bytes:
    """
    Args:
        result: the ATPResult straight out of ATPEngine.compute() (same
            input type as summary_generator.build_summary /
            missing_generator.build_missing).

    Returns:
        Raw .zip bytes containing one "<SellerID>_<sanitized seller
        name>.xlsx" per seller with a NOT-ATP row.
    """
    rows = result.dkpc_results
    rows = rows.loc[
        (~rows["is_atp"]) & rows[C.NET_ITEM_FCAST].notna() & (rows[C.NET_ITEM_FCAST] > 0)
    ].copy()

    buffer = io.BytesIO()
    seller_count = 0
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for seller_id, group in rows.groupby(C.SELLER_ID, sort=True):
            ordered = group.sort_values(C.NET_ITEM_FCAST, ascending=False, kind="stable")
            seller_name = ordered[C.SELLER].iloc[0] if len(ordered) else ""
            sheet = pd.DataFrame(
                {
                    SELLER_ID_COLUMN: ordered[C.SELLER_ID],
                    SELLER_COLUMN: ordered[C.SELLER],
                    DKP_COLUMN: ordered[C.DKP],
                    DKPC_COLUMN: ordered[C.DKPC],
                    WEIGHT_COLUMN: ordered[C.WEIGHT],
                    CATEGORY_COLUMN: ordered[C.CATEGORY],
                    BUCKET_COLUMN: ordered[C.BUCKET],
                    TAIL_BADGE_COLUMN: ordered[C.TAIL_BADGE],
                }
            )
            xlsx_bytes = dataframe_to_excel_bytes(sheet, sheet_name="ATP_Missing")
            filename = f"{_safe_filename_part(seller_id)}_{_safe_filename_part(seller_name)}.xlsx"
            zf.writestr(filename, xlsx_bytes)
            seller_count += 1

    logger.info("Built per-seller ZIP export for %d seller(s).", seller_count)
    buffer.seek(0)
    return buffer.read()
