from io import BytesIO

import pandas as pd
import pytest

from backend.excel_loader import ExcelValidationError, load_live_data, load_sold_data


def _to_xlsx_bytes(df: pd.DataFrame) -> BytesIO:
    buf = BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)
    return buf


def _to_csv_bytes(df: pd.DataFrame, *, encoding: str = "utf-8-sig", sep: str = ",") -> BytesIO:
    buf = BytesIO()
    df.to_csv(buf, index=False, encoding=encoding, sep=sep)
    buf.seek(0)
    return buf


def test_load_live_data_happy_path():
    df = pd.DataFrame(
        {
            "Seller_ID": ["S1", "S2"],
            "Seller_Name": ["ACME", " Beta Co "],
            "DKP": ["D1", "D2"],
            "DKPC": ["D1C1", "D2C1"],
            "Size_Name": ["0.65 گرم", 2.5],
        }
    )
    result = load_live_data(_to_xlsx_bytes(df))
    assert list(result.df["seller_id"]) == ["S1", "S2"]
    assert list(result.df["seller"]) == ["ACME", "Beta Co"]
    assert list(result.df["seller_key"]) == ["s1", "s2"]
    assert result.df["weight"].tolist() == [0.65, 2.5]
    assert result.warnings == []


def test_load_live_data_missing_column_raises():
    df = pd.DataFrame({"Seller_Name": ["ACME"], "DKP": ["D1"]})  # missing Seller_ID, DKPC, Size_Name
    with pytest.raises(ExcelValidationError):
        load_live_data(_to_xlsx_bytes(df))


def test_load_live_data_missing_seller_id_column_raises():
    df = pd.DataFrame(
        {
            "Seller_Name": ["ACME"],
            "DKP": ["D1"],
            "DKPC": ["D1C1"],
            "Size_Name": [1.0],
        }
    )
    with pytest.raises(ExcelValidationError):
        load_live_data(_to_xlsx_bytes(df))


def test_load_live_data_drops_rows_missing_identifiers_and_warns():
    df = pd.DataFrame(
        {
            "Seller_ID": ["S1", None, "S3"],
            "Seller_Name": ["ACME", "Beta", "Gamma"],
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
            "Seller_ID": ["S1"],
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


def test_seller_id_with_float_upcast_is_normalized():
    # A blank cell elsewhere in an ID column upcasts the whole column to
    # float64 in pandas (e.g. 20911381.0 instead of "20911381").
    df = pd.DataFrame(
        {
            "Seller_ID": [20911381.0, 20911382.0],
            "Seller_Name": ["ACME", "Beta"],
            "DKP": ["D1", "D2"],
            "DKPC": ["D1C1", "D2C1"],
            "Size_Name": [1.0, 2.0],
        }
    )
    result = load_live_data(_to_xlsx_bytes(df))
    assert list(result.df["seller_id"]) == ["20911381", "20911382"]


def test_dkp_dkpc_with_float_upcast_are_normalized():
    df = pd.DataFrame(
        {
            "Seller_ID": ["S1", "S2"],
            "Seller_Name": ["ACME", "Beta"],
            "DKP": [551306.0, 551307.0],
            "DKPC": [59916616.0, 59916617.0],
            "Size_Name": [1.0, 2.0],
        }
    )
    result = load_live_data(_to_xlsx_bytes(df))
    assert list(result.df["dkp"]) == ["551306", "551307"]
    assert list(result.df["dkpc"]) == ["59916616", "59916617"]


def test_load_sold_data_happy_path_extracts_weight_from_product_variant_name():
    df = pd.DataFrame(
        {
            "marketplace_seller_id": ["S1"],
            "marketplace_seller_name": ["ACME"],
            "product_id": ["D1"],
            "product_variant_id": ["D1C1"],
            "product_variant_name_fa": ["choco bar | 0.65 گرم |"],
            "category_name_fa": ["زیورآلات"],
            "sum_net_item_fcast": [5],
        }
    )
    result = load_sold_data(_to_xlsx_bytes(df))
    assert result.df["weight"].iloc[0] == pytest.approx(0.65)
    assert result.df["seller_id"].iloc[0] == "S1"
    assert result.df["category"].iloc[0] == "زیورآلات"
    assert result.df["net_item_fcast"].iloc[0] == pytest.approx(5)


def test_load_sold_data_extracts_weight_from_plain_numeric_product_variant_name():
    df = pd.DataFrame(
        {
            "marketplace_seller_id": ["S1"],
            "marketplace_seller_name": ["ACME"],
            "product_id": ["D1"],
            "product_variant_id": ["D1C1"],
            "product_variant_name_fa": [0.5],
            "category_name_fa": ["شمش"],
            "sum_net_item_fcast": [1],
        }
    )
    result = load_sold_data(_to_xlsx_bytes(df))
    assert result.df["weight"].iloc[0] == pytest.approx(0.5)


def test_load_sold_data_allows_blank_category_and_net_item_fcast():
    df = pd.DataFrame(
        {
            "marketplace_seller_id": ["S1"],
            "marketplace_seller_name": ["ACME"],
            "product_id": ["D1"],
            "product_variant_id": ["D1C1"],
            "product_variant_name_fa": [0.5],
            "category_name_fa": [None],
            "sum_net_item_fcast": [None],
        }
    )
    result = load_sold_data(_to_xlsx_bytes(df))
    assert len(result.df) == 1
    assert result.df["category"].iloc[0] == ""
    assert pd.isna(result.df["net_item_fcast"].iloc[0])


def test_load_sold_data_missing_column_raises():
    df = pd.DataFrame({"marketplace_seller_name": ["ACME"]})
    with pytest.raises(ExcelValidationError):
        load_sold_data(_to_xlsx_bytes(df))


def test_load_sold_data_missing_category_or_net_item_fcast_column_raises():
    df = pd.DataFrame(
        {
            "marketplace_seller_id": ["S1"],
            "marketplace_seller_name": ["ACME"],
            "product_id": ["D1"],
            "product_variant_id": ["D1C1"],
            "product_variant_name_fa": [0.5],
            # category_name_fa / sum_net_item_fcast intentionally omitted
        }
    )
    with pytest.raises(ExcelValidationError):
        load_sold_data(_to_xlsx_bytes(df))


def test_seller_id_is_the_join_key_not_seller_name():
    live_df = pd.DataFrame(
        {
            "Seller_ID": ["S2"],
            "Seller_Name": [" Beta Co "],
            "DKP": ["D2"],
            "DKPC": ["D2C1"],
            "Size_Name": [2.5],
        }
    )
    # Same Seller_ID, different display name -> same seller_key.
    sold_df_same_id = pd.DataFrame(
        {
            "marketplace_seller_id": ["S2"],
            "marketplace_seller_name": ["Totally Different Name"],
            "product_id": ["D2"],
            "product_variant_id": ["D2C1"],
            "product_variant_name_fa": ["item"],
            "category_name_fa": [""],
            "sum_net_item_fcast": [0],
        }
    )
    live_result = load_live_data(_to_xlsx_bytes(live_df))
    sold_result_same_id = load_sold_data(_to_xlsx_bytes(sold_df_same_id))
    assert live_result.df["seller_key"].iloc[0] == sold_result_same_id.df["seller_key"].iloc[0]
    assert live_result.df["seller"].iloc[0] == "Beta Co"
    assert sold_result_same_id.df["seller"].iloc[0] == "Totally Different Name"

    # Same display name, different Seller_ID -> different seller_key.
    sold_df_diff_id = pd.DataFrame(
        {
            "marketplace_seller_id": ["S99"],
            "marketplace_seller_name": ["Beta Co"],
            "product_id": ["D2"],
            "product_variant_id": ["D2C1"],
            "product_variant_name_fa": ["item"],
            "category_name_fa": [""],
            "sum_net_item_fcast": [0],
        }
    )
    sold_result_diff_id = load_sold_data(_to_xlsx_bytes(sold_df_diff_id))
    assert live_result.df["seller_key"].iloc[0] != sold_result_diff_id.df["seller_key"].iloc[0]


def test_load_live_data_reads_csv_when_filename_ends_with_csv():
    df = pd.DataFrame(
        {
            "Seller_ID": ["S1"],
            "Seller_Name": ["ACME"],
            "DKP": ["D1"],
            "DKPC": ["D1C1"],
            "Size_Name": ["0.65 گرم"],
        }
    )
    result = load_live_data(_to_csv_bytes(df), filename="Live_Data.csv")
    assert result.df["seller_id"].iloc[0] == "S1"
    assert result.df["weight"].iloc[0] == pytest.approx(0.65)


def test_load_sold_data_reads_csv_when_filename_ends_with_csv():
    df = pd.DataFrame(
        {
            "marketplace_seller_id": ["S1"],
            "marketplace_seller_name": ["ACME"],
            "product_id": ["D1"],
            "product_variant_id": ["D1C1"],
            "product_variant_name_fa": [0.5],
            "category_name_fa": ["شمش"],
            "sum_net_item_fcast": [3],
        }
    )
    result = load_sold_data(_to_csv_bytes(df), filename="Sold_Data.CSV")
    assert result.df["weight"].iloc[0] == pytest.approx(0.5)
    assert result.df["category"].iloc[0] == "شمش"


def test_load_data_csv_delimiter_is_auto_detected():
    df = pd.DataFrame(
        {
            "marketplace_seller_id": ["S1"],
            "marketplace_seller_name": ["ACME"],
            "product_id": ["D1"],
            "product_variant_id": ["D1C1"],
            "product_variant_name_fa": [0.5],
            "category_name_fa": ["زیورآلات"],
            "sum_net_item_fcast": [1],
        }
    )
    result = load_sold_data(_to_csv_bytes(df, sep=";"), filename="Sold_Data.csv")
    assert result.df["seller_id"].iloc[0] == "S1"


def test_xlsx_filename_is_not_treated_as_csv():
    # Sanity check: without a .csv filename, xlsx bytes load as before.
    df = pd.DataFrame(
        {
            "Seller_ID": ["S1"],
            "Seller_Name": ["ACME"],
            "DKP": ["D1"],
            "DKPC": ["D1C1"],
            "Size_Name": [1.0],
        }
    )
    result = load_live_data(_to_xlsx_bytes(df), filename="Live_Data.xlsx")
    assert result.df["seller_id"].iloc[0] == "S1"
