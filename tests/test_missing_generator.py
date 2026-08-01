import pandas as pd
import pytest

from backend.atp_engine import ATPResult
from backend.config import CanonicalColumns as C
from backend.config import CategoryBucket
from backend.missing_generator import build_missing


def _row(dkpc, is_atp, **overrides) -> dict:
    row = {
        C.SELLER_ID: "S1",
        C.SELLER: "ACME",
        C.DKP: "D1",
        C.DKPC: dkpc,
        C.CATEGORY: "زیورآلات",
        C.BUCKET: CategoryBucket.JEWELRY,
        "is_atp": is_atp,
    }
    row.update(overrides)
    return row


def test_missing_only_lists_not_atp_rows():
    rows = [_row("D1C1", is_atp=False), _row("D1C2", is_atp=True)]
    result = ATPResult(dkpc_results=pd.DataFrame(rows), dkp_results=pd.DataFrame())
    missing = build_missing(result)
    assert list(missing["DKPC"]) == ["D1C1"]


def test_missing_includes_seller_id_column():
    rows = [_row("D1C1", is_atp=False)]
    result = ATPResult(dkpc_results=pd.DataFrame(rows), dkp_results=pd.DataFrame())
    missing = build_missing(result)
    assert missing.iloc[0]["Seller ID"] == "S1"


def test_missing_includes_category_and_bucket_columns():
    rows = [_row("D1C1", is_atp=False, **{C.CATEGORY: "شمش", C.BUCKET: CategoryBucket.BULLION})]
    result = ATPResult(dkpc_results=pd.DataFrame(rows), dkp_results=pd.DataFrame())
    missing = build_missing(result)
    assert missing.iloc[0]["Category"] == "شمش"
    assert missing.iloc[0]["Bucket"] == CategoryBucket.BULLION
    assert list(missing.columns) == ["Seller ID", "Seller", "DKP", "DKPC", "Category", "Bucket"]
