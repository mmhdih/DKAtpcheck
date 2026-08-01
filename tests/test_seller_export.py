import io
import zipfile

import pandas as pd
import pytest

from backend.atp_engine import ATPResult
from backend.config import CanonicalColumns as C
from backend.config import CategoryBucket
from backend.seller_export import build_seller_missing_zip


def _dkpc_row(**overrides) -> dict:
    row = {
        C.SELLER_ID: "S1",
        C.SELLER: "ACME",
        C.DKP: "D1",
        C.DKPC: "D1C1",
        C.WEIGHT: 1.0,
        C.CATEGORY: "زیورآلات",
        C.BUCKET: CategoryBucket.JEWELRY,
        C.TAIL_BADGE: "ST",
        C.NET_ITEM_FCAST: 10.0,
        "match_type": "not_atp",
        "is_atp": False,
    }
    row.update(overrides)
    return row


def _result(rows: list[dict]) -> ATPResult:
    dkpc_df = pd.DataFrame(rows)
    return ATPResult(dkpc_results=dkpc_df, dkp_results=pd.DataFrame())


def _read_zip_sheets(zip_bytes: bytes) -> dict[str, pd.DataFrame]:
    sheets = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            sheets[name] = pd.read_excel(io.BytesIO(zf.read(name)))
    return sheets


def test_zip_contains_one_file_per_seller_id():
    rows = [
        _dkpc_row(**{C.SELLER_ID: "S1", C.DKPC: "D1C1"}),
        _dkpc_row(**{C.SELLER_ID: "S2", C.DKPC: "D1C2"}),
    ]
    zip_bytes = build_seller_missing_zip(_result(rows))
    sheets = _read_zip_sheets(zip_bytes)
    assert len(sheets) == 2


def test_zip_excludes_atp_rows():
    rows = [
        _dkpc_row(**{"is_atp": False, C.DKPC: "MISSING1"}),
        _dkpc_row(**{"is_atp": True, C.DKPC: "ATP1"}),
    ]
    zip_bytes = build_seller_missing_zip(_result(rows))
    sheets = _read_zip_sheets(zip_bytes)
    all_dkpc = pd.concat(sheets.values())["DKPC"].tolist()
    assert "MISSING1" in all_dkpc
    assert "ATP1" not in all_dkpc


def test_zip_excludes_zero_or_blank_net_item_fcast_rows():
    rows = [
        _dkpc_row(**{C.DKPC: "ZERO", C.NET_ITEM_FCAST: 0.0}),
        _dkpc_row(**{C.DKPC: "BLANK", C.NET_ITEM_FCAST: float("nan")}),
        _dkpc_row(**{C.DKPC: "REAL", C.NET_ITEM_FCAST: 3.0}),
    ]
    zip_bytes = build_seller_missing_zip(_result(rows))
    sheets = _read_zip_sheets(zip_bytes)
    all_dkpc = pd.concat(sheets.values())["DKPC"].tolist()
    assert all_dkpc == ["REAL"]


def test_zip_sorted_by_net_item_fcast_descending_and_excludes_that_column():
    rows = [
        _dkpc_row(**{C.DKPC: "LOW", C.NET_ITEM_FCAST: 1.0}),
        _dkpc_row(**{C.DKPC: "HIGH", C.NET_ITEM_FCAST: 99.0}),
        _dkpc_row(**{C.DKPC: "MID", C.NET_ITEM_FCAST: 50.0}),
    ]
    zip_bytes = build_seller_missing_zip(_result(rows))
    sheets = _read_zip_sheets(zip_bytes)
    sheet = next(iter(sheets.values()))
    assert list(sheet["DKPC"]) == ["HIGH", "MID", "LOW"]
    assert "net_item_fcast" not in sheet.columns
    assert "Net Item Fcast" not in sheet.columns


def test_zip_filename_is_sanitized_and_includes_seller_id():
    rows = [_dkpc_row(**{C.SELLER_ID: "S 1/../weird", C.SELLER: "ACME Co."})]
    zip_bytes = build_seller_missing_zip(_result(rows))
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
    assert len(names) == 1
    assert "/" not in names[0]
    assert "\\" not in names[0]
    assert names[0].startswith("S_1")
    assert names[0].endswith(".xlsx")


def test_zip_filename_uses_seller_id_dash_seller_name_format():
    rows = [_dkpc_row(**{C.SELLER_ID: "42", C.SELLER: "ACME"})]
    zip_bytes = build_seller_missing_zip(_result(rows))
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
    assert names == ["42-ACME.xlsx"]


def test_zip_output_columns_are_exactly_the_expected_set():
    rows = [_dkpc_row()]
    zip_bytes = build_seller_missing_zip(_result(rows))
    sheets = _read_zip_sheets(zip_bytes)
    sheet = next(iter(sheets.values()))
    assert list(sheet.columns) == [
        "Seller ID", "Seller", "DKP", "DKPC", "Weight", "Category", "Bucket", "Tail Badge",
    ]
