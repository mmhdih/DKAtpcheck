from io import BytesIO

import pandas as pd
import pytest

from backend import field_names as fn
from backend.excel_loader import load_live_data


@pytest.fixture(autouse=True)
def _isolated_settings_file(tmp_path, monkeypatch):
    """Never touch the real user home directory while testing."""
    monkeypatch.setattr(fn, "_SETTINGS_DIR", tmp_path / ".atp_analyzer")
    monkeypatch.setattr(fn, "_SETTINGS_FILE", tmp_path / ".atp_analyzer" / "field_names.json")
    yield


def test_get_field_names_returns_defaults_when_nothing_saved():
    assert fn.get_field_names() == fn.DEFAULT_FIELD_NAMES


def test_save_field_names_persists_and_merges():
    fn.save_field_names({"live_weight": "Weight_New"})
    names = fn.get_field_names()
    assert names["live_weight"] == "Weight_New"
    # Everything else stays at its default.
    assert names["live_seller_id"] == fn.DEFAULT_FIELD_NAMES["live_seller_id"]

    # A second, partial save doesn't wipe out the first override.
    fn.save_field_names({"sold_category": "Category_Persian"})
    names = fn.get_field_names()
    assert names["live_weight"] == "Weight_New"
    assert names["sold_category"] == "Category_Persian"


def test_save_field_names_ignores_unknown_and_blank_values():
    fn.save_field_names({"not_a_real_key": "x", "live_weight": "  "})
    assert fn.get_field_names() == fn.DEFAULT_FIELD_NAMES


def test_saving_the_default_value_clears_the_override():
    fn.save_field_names({"live_weight": "Weight_New"})
    fn.save_field_names({"live_weight": fn.DEFAULT_FIELD_NAMES["live_weight"]})
    assert fn.get_field_names()["live_weight"] == fn.DEFAULT_FIELD_NAMES["live_weight"]


def test_reset_field_names_reverts_everything():
    fn.save_field_names({"live_weight": "Weight_New", "sold_category": "Category_Persian"})
    fn.reset_field_names()
    assert fn.get_field_names() == fn.DEFAULT_FIELD_NAMES


def test_dkp_name_column_is_editable_and_defaults_to_dkp_name():
    assert fn.DEFAULT_FIELD_NAMES["live_dkp_name"] == "DKP Name"
    fn.save_field_names({"live_dkp_name": "Product Title"})
    assert fn.get_field_names()["live_dkp_name"] == "Product Title"


def test_excel_loader_honors_renamed_dkp_name_column():
    fn.save_field_names({"live_dkp_name": "Product Title"})
    df = pd.DataFrame(
        {
            "Seller_ID": ["S1"],
            "Seller_Name": ["ACME"],
            "DKP": ["D1"],
            "Product Title": ["Gold bracelet"],
            "DKPC": ["D1C1"],
            "Weight": [2.5],
        }
    )
    buf = BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)

    result = load_live_data(buf)
    assert list(result.df["dkp_name"]) == ["Gold bracelet"]
    assert result.warnings == []


def test_excel_loader_honors_saved_field_name_override():
    fn.save_field_names({"live_weight": "Renamed_Weight_Column"})
    df = pd.DataFrame(
        {
            "Seller_ID": ["S1"],
            "Seller_Name": ["ACME"],
            "DKP": ["D1"],
            "DKPC": ["D1C1"],
            "Renamed_Weight_Column": [2.5],
        }
    )
    buf = BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)

    result = load_live_data(buf)
    assert result.df["weight"].iloc[0] == pytest.approx(2.5)
