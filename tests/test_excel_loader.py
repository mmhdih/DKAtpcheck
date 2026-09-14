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
            "DKP Name": ["Gold bracelet", " شمش طلا "],
            "DKPC": ["D1C1", "D2C1"],
            "Weight": ["0.65 گرم", 2.5],
        }
    )
    result = load_live_data(_to_xlsx_bytes(df))
    assert list(result.df["seller_id"]) == ["S1", "S2"]
    assert list(result.df["seller"]) == ["ACME", "Beta Co"]
    assert list(result.df["seller_key"]) == ["s1", "s2"]
    assert list(result.df["dkp_name"]) == ["Gold bracelet", "شمش طلا"]
    assert result.df["weight"].tolist() == [0.65, 2.5]
    assert result.warnings == []


def test_load_live_data_without_dkp_name_column_warns_but_still_loads():
    # The product name only enriches reports, so an assortment export that
    # doesn't carry it must not be rejected.
    df = pd.DataFrame(
        {
            "Seller_ID": ["S1"],
            "Seller_Name": ["ACME"],
            "DKP": ["D1"],
            "DKPC": ["D1C1"],
            "Weight": [1.0],
        }
    )
    result = load_live_data(_to_xlsx_bytes(df))
    assert len(result.df) == 1
    assert list(result.df["dkp_name"]) == [""]
    assert any("DKP Name" in w for w in result.warnings)


def test_load_live_data_missing_column_raises():
    df = pd.DataFrame({"Seller_Name": ["ACME"], "DKP": ["D1"]})  # missing Seller_ID, DKPC, Weight
    with pytest.raises(ExcelValidationError):
        load_live_data(_to_xlsx_bytes(df))


def test_load_live_data_missing_seller_id_column_raises():
    df = pd.DataFrame(
        {
            "Seller_Name": ["ACME"],
            "DKP": ["D1"],
            "DKPC": ["D1C1"],
            "Weight": [1.0],
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
            "Weight": [1.0, 2.0, 3.0],
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
            "Weight": ["no weight here"],
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
            "Weight": [1.0, 2.0],
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
            "Weight": [1.0, 2.0],
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
            "Weight": [2.5],
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
            "Weight": ["0.65 گرم"],
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
            "Weight": [1.0],
        }
    )
    result = load_live_data(_to_xlsx_bytes(df), filename="Live_Data.xlsx")
    assert result.df["seller_id"].iloc[0] == "S1"


# --------------------------------------------------------------------------- #
# Header matching — a header that differs only cosmetically is the same column
# --------------------------------------------------------------------------- #
def _live_df(dkp_name_header: str = "DKP Name", **header_overrides: str) -> pd.DataFrame:
    headers = {
        "seller_id": "Seller_ID", "seller": "Seller_Name", "dkp": "DKP",
        "dkpc": "DKPC", "weight": "Weight",
    }
    headers.update(header_overrides)
    return pd.DataFrame(
        {
            headers["seller_id"]: ["S1"],
            headers["seller"]: ["ACME"],
            headers["dkp"]: ["D1"],
            dkp_name_header: ["دستبند طلا"],
            headers["dkpc"]: ["D1C1"],
            headers["weight"]: [1.0],
        }
    )


@pytest.mark.parametrize(
    "header",
    ["DKP Name", "DKP_Name", "DKP NAME", "dkp name", "DKP Name ", "Dkp-Name"],
)
def test_product_name_column_matches_despite_case_separator_or_padding(header):
    result = load_live_data(_to_xlsx_bytes(_live_df(header)))
    assert list(result.df["dkp_name"]) == ["دستبند طلا"]
    assert result.warnings == []


@pytest.mark.parametrize("header", ["نام کالا", "Product Name", "Product Title"])
def test_product_name_column_matches_known_alternative_spellings(header):
    result = load_live_data(_to_xlsx_bytes(_live_df(header)))
    assert list(result.df["dkp_name"]) == ["دستبند طلا"]


def test_unknown_product_name_header_warns_with_the_files_actual_columns():
    result = load_live_data(_to_xlsx_bytes(_live_df("Totally Unexpected")))
    assert list(result.df["dkp_name"]) == [""]
    warning = next(w for w in result.warnings if "product-name" in w)
    # The warning has to name what IS in the file, so the column can be
    # fixed in Settings without guessing.
    assert "Totally Unexpected" in warning


def test_empty_product_name_column_warns_rather_than_passing_silently():
    df = _live_df()
    df["DKP Name"] = ""
    result = load_live_data(_to_xlsx_bytes(df))
    assert any("present but empty" in w for w in result.warnings)


def test_required_columns_also_match_despite_case_and_separator():
    df = _live_df(seller_id="seller id", seller="SELLER_NAME", weight="weight")
    result = load_live_data(_to_xlsx_bytes(df))
    assert list(result.df["seller_id"]) == ["S1"]
    assert list(result.df["seller"]) == ["ACME"]
    assert result.df["weight"].tolist() == [1.0]


def test_sold_data_required_columns_match_despite_case_and_separator():
    df = pd.DataFrame(
        {
            "Marketplace_Seller_ID": ["S1"],
            "marketplace seller name": ["ACME"],
            "Product_ID": ["D1"],
            "product variant id": ["D1C1"],
            "product_variant_name_fa": ["0.65 گرم"],
            "Category_Name_FA": ["زیورآلات"],
            "Sum Net Item Fcast": [5],
        }
    )
    result = load_sold_data(_to_xlsx_bytes(df))
    assert result.df["seller_id"].iloc[0] == "S1"
    assert result.df["category"].iloc[0] == "زیورآلات"
    assert result.df["net_item_fcast"].iloc[0] == pytest.approx(5)


def test_ambiguous_duplicate_headers_are_not_guessed_at():
    # Two headers folding to the same key: picking either would be a coin
    # flip, so the column counts as missing instead.
    df = _live_df()
    df.insert(0, "seller id", ["OTHER"])
    with pytest.raises(ExcelValidationError):
        load_live_data(_to_xlsx_bytes(df.rename(columns={"Seller_ID": "Seller ID"})))


def test_weight_header_named_exactly_weight_does_not_clobber_the_parsed_weight():
    # Regression: the raw weight text used to be parked under its own
    # header, so a file whose weight column is literally "weight" collided
    # with the canonical weight column — and dropping the raw one dropped
    # the parsed weights with it.
    df = _live_df(weight="weight")
    df["weight"] = ["0.65 گرم"]
    result = load_live_data(_to_xlsx_bytes(df))
    assert result.df["weight"].tolist() == [0.65]
