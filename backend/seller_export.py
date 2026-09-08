"""
seller_export.py
-----------------
Builds a ZIP of one styled .xlsx per Seller ID, listing that seller's
NOT-ATP sold DKPCs — the actionable "make these live again" hand-off cut
of the on-screen Seller ATP DKPC table: the same badged rows carrying
the same per-seller Item-Tail badge, narrowed to the Unavailable ones and
enriched with Weight. Rows whose DKP has no badge at all (zero/blank
forecast volume) are excluded, exactly as they are from that table; the
raw net_item_fcast number only pre-sorts what remains, biggest demand
first, and is never written to the output.

Reuses utils.dataframe_to_excel_bytes for the actual xlsx styling.
"""
from __future__ import annotations

import io
import zipfile

import pandas as pd

from .atp_engine import ATPResult
from .config import CanonicalColumns as C
from .config import TailClassification
from .report_labels import TAIL_BADGE_COLORS, TAIL_BADGE_COLUMN
from .utils import dataframe_to_excel_bytes, get_logger, safe_filename_part

logger = get_logger(__name__)

SELLER_ID_COLUMN = "Seller ID"
SELLER_COLUMN = "Seller"
DKP_COLUMN = "DKP"
DKP_NAME_COLUMN = "DKP Name"
DKPC_COLUMN = "DKPC"
WEIGHT_COLUMN = "Weight"
CATEGORY_COLUMN = "Category"
BUCKET_COLUMN = "Bucket"


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
        (~rows["is_atp"]) & rows[C.TAIL_BADGE].isin(TailClassification.ALL)
    ].copy()

    buffer = io.BytesIO()
    seller_count = 0
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for seller_id, group in rows.groupby(C.SELLER_ID, sort=True):
            ordered = group.sort_values(
                C.NET_ITEM_FCAST, ascending=False, kind="stable", na_position="last"
            )
            seller_name = ordered[C.SELLER].iloc[0] if len(ordered) else ""
            sheet = pd.DataFrame(
                {
                    SELLER_ID_COLUMN: ordered[C.SELLER_ID],
                    SELLER_COLUMN: ordered[C.SELLER],
                    DKP_COLUMN: ordered[C.DKP],
                    DKP_NAME_COLUMN: ordered[C.DKP_NAME],
                    DKPC_COLUMN: ordered[C.DKPC],
                    WEIGHT_COLUMN: ordered[C.WEIGHT],
                    CATEGORY_COLUMN: ordered[C.CATEGORY],
                    BUCKET_COLUMN: ordered[C.BUCKET],
                    TAIL_BADGE_COLUMN: ordered[C.TAIL_BADGE],
                }
            )
            xlsx_bytes = dataframe_to_excel_bytes(
                sheet,
                sheet_name="ATP_DKPC",
                categorical_color_columns={TAIL_BADGE_COLUMN: TAIL_BADGE_COLORS},
            )
            filename = f"{safe_filename_part(seller_id)}-{safe_filename_part(seller_name)}.xlsx"
            zf.writestr(filename, xlsx_bytes)
            seller_count += 1

    logger.info("Built per-seller ZIP export for %d seller(s).", seller_count)
    buffer.seek(0)
    return buffer.read()
