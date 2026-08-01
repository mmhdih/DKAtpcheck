import pandas as pd
import pytest

from backend.atp_engine import ATPResult
from backend.config import CanonicalColumns as C
from backend.config import CategoryBucket
from backend.summary_generator import build_summary


def _dkpc_row(seller_id, seller, is_atp, bucket) -> dict:
    return {
        C.SELLER_ID: seller_id,
        C.SELLER: seller,
        C.SELLER_KEY: seller_id.casefold(),
        C.BUCKET: bucket,
        "is_atp": is_atp,
    }


def _dkp_row(seller_id, seller, is_atp, bucket) -> dict:
    return {
        C.SELLER_ID: seller_id,
        C.SELLER: seller,
        C.SELLER_KEY: seller_id.casefold(),
        C.BUCKET: bucket,
        "is_atp": is_atp,
    }


def test_summary_splits_bullion_and_jewelry_percentages_independently():
    dkpc_rows = [
        _dkpc_row("S1", "ACME", True, CategoryBucket.BULLION),
        _dkpc_row("S1", "ACME", False, CategoryBucket.BULLION),
        _dkpc_row("S1", "ACME", True, CategoryBucket.JEWELRY),
        _dkpc_row("S1", "ACME", True, CategoryBucket.JEWELRY),
    ]
    dkp_rows = [
        _dkp_row("S1", "ACME", True, CategoryBucket.BULLION),
        _dkp_row("S1", "ACME", False, CategoryBucket.JEWELRY),
    ]
    result = ATPResult(dkpc_results=pd.DataFrame(dkpc_rows), dkp_results=pd.DataFrame(dkp_rows))
    summary = build_summary(result)
    row = summary.iloc[0]
    assert row["DKPC ATP % (Bullion)"] == 50.0
    assert row["DKPC ATP % (Jewelry)"] == 100.0
    assert row["DKP ATP % (Bullion)"] == 100.0
    assert row["DKP ATP % (Jewelry)"] == 0.0


def test_summary_fills_zero_when_seller_has_no_rows_in_one_bucket():
    dkpc_rows = [_dkpc_row("S1", "ACME", True, CategoryBucket.JEWELRY)]
    dkp_rows = [_dkp_row("S1", "ACME", True, CategoryBucket.JEWELRY)]
    result = ATPResult(dkpc_results=pd.DataFrame(dkpc_rows), dkp_results=pd.DataFrame(dkp_rows))
    summary = build_summary(result)
    row = summary.iloc[0]
    assert row["DKPC ATP % (Bullion)"] == 0.0
    assert row["DKP ATP % (Bullion)"] == 0.0
    assert row["DKPC ATP % (Jewelry)"] == 100.0


def test_summary_includes_seller_id_and_seller_columns():
    dkpc_rows = [_dkpc_row("S1", "ACME", True, CategoryBucket.JEWELRY)]
    dkp_rows = [_dkp_row("S1", "ACME", True, CategoryBucket.JEWELRY)]
    result = ATPResult(dkpc_results=pd.DataFrame(dkpc_rows), dkp_results=pd.DataFrame(dkp_rows))
    summary = build_summary(result)
    assert list(summary.columns)[:2] == ["Seller ID", "Seller"]
    assert summary.iloc[0]["Seller ID"] == "S1"
    assert summary.iloc[0]["Seller"] == "ACME"
