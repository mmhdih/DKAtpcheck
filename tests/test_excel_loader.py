from io import BytesIO

import pandas as pd
import pytest

from backend.excel_loader import ExcelValidationError, load_live_data, load_sold_data


def _to_xlsx_bytes(df: pd.DataFrame) -> BytesIO:
    buf = BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)
    return buf


def test_load_live_data_happy_path():
    df = pd.DataFrame(
        {
            "Seller_Name": ["ACME", " Beta Co "],
            "DKP": ["D1", "D2"],
            "DKPC": ["D1C1", "D2C1"],
            "Size_Name": ["0.65 گرم", 2.5],
        }
    )
    result = load_live_data(_to_xlsx_bytes(df))
    assert list(result.df["seller"]) == ["ACME", "Beta Co"]
    assert list(result.df["seller_key"]) == ["acme", "beta co"]
    assert result.df["weight"].tolist() == [0.65, 2.5]
    assert result.warnings == []


def test_load_live_data_missing_column_raises():
    df = pd.DataFrame({"Seller_Name": ["ACME"], "DKP": ["D1"]})  # missing DKPC, Size_Name
    with pytest.raises(ExcelValidationError):
        load_live_data(_to_xlsx_bytes(df))


def test_load_live_data_drops_rows_missing_identifiers_and_warns():
    df = pd.DataFrame(
        {
            "Seller_Name": ["ACME", None, "Gamma"],
            "DKP": ["D1", "D2", "D3"],
            "DKPC": ["D1C1", "D2C1", "D3C1"],
            "Size_Name": [1.0, 2.0, 3.0],
        }
    )
    result = load_live_data(_to_xlsx_bytes(df))
    assert len(result.df) == 2
    assert any("dropped" in w.lower() for w in result.warnings)


def test_load_live_data_unresolvable_weight_warns_but_keeps_row():
    df = pd.DataFrame(
        {
            "Seller_Name": ["ACME"],
            "DKP": ["D1"],
            "DKPC": ["D1C1"],
            "Size_Name": ["no weight here"],
        }
    )
    result = load_live_data(_to_xlsx_bytes(df))
    assert len(result.df) == 1
    assert result.df["weight"].isna().all()
    assert any("unresolvable" in w.lower() for w in result.warnings)


def test_load_sold_data_happy_path_extracts_weight_from_product_name():
    df = pd.DataFrame(
        {
            "Seller Name": ["ACME"],
            "Product Id": ["D1"],
            "Product Item Id": ["D1C1"],
            "Product Item Name": ["choco bar | 0.65 گرم |"],
        }
    )
    result = load_sold_data(_to_xlsx_bytes(df))
    assert result.df["weight"].iloc[0] == pytest.approx(0.65)


def test_load_sold_data_missing_column_raises():
    df = pd.DataFrame({"Seller Name": ["ACME"]})
    with pytest.raises(ExcelValidationError):
        load_sold_data(_to_xlsx_bytes(df))


def test_seller_keys_are_case_and_whitespace_insensitive_across_files():
    live_df = pd.DataFrame(
        {
            "Seller_Name": [" Beta Co "],
            "DKP": ["D2"],
            "DKPC": ["D2C1"],
            "Size_Name": [2.5],
        }
    )
    sold_df = pd.DataFrame(
        {
            "Seller Name": ["beta co"],
            "Product Id": ["D2"],
            "Product Item Id": ["D2C1"],
            "Product Item Name": ["item"],
        }
    )
    live_result = load_live_data(_to_xlsx_bytes(live_df))
    sold_result = load_sold_data(_to_xlsx_bytes(sold_df))
    assert live_result.df["seller_key"].iloc[0] == sold_result.df["seller_key"].iloc[0]
    # Display casing is preserved independently per file.
    assert live_result.df["seller"].iloc[0] == "Beta Co"
    assert sold_result.df["seller"].iloc[0] == "beta co"
