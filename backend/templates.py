"""
templates.py
-------------
Builds downloadable, correctly-headed example Excel files for Live_Data
and Sold_Data, generated on the fly from the raw column constants in
config.py so they can never drift out of sync with the schema the loaders
actually require.
"""
from __future__ import annotations

import pandas as pd

from .config import LiveDataColumns, SoldDataColumns
from .utils import dataframe_to_excel_bytes

LIVE_DATA_EXAMPLE_ROW = {
    LiveDataColumns.SELLER_ID: "10001",
    LiveDataColumns.SELLER: "Sample Seller",
    LiveDataColumns.DKP: "551306",
    LiveDataColumns.DKPC: "59916616",
    LiveDataColumns.SIZE_NAME: "0.65 گرم",
}

SOLD_DATA_EXAMPLE_ROW = {
    SoldDataColumns.SELLER_ID: "10001",
    SoldDataColumns.SELLER: "Sample Seller",
    SoldDataColumns.DKP: "551306",
    SoldDataColumns.DKPC: "59916616",
    SoldDataColumns.WEIGHT_SOURCE: "0.65 گرم",
    SoldDataColumns.CATEGORY: "زیورآلات",
    SoldDataColumns.NET_ITEM_FCAST: 12,
}


def build_live_data_template_bytes() -> bytes:
    df = pd.DataFrame([LIVE_DATA_EXAMPLE_ROW], columns=list(LiveDataColumns.REQUIRED))
    return dataframe_to_excel_bytes(df, sheet_name="Live_Data")


def build_sold_data_template_bytes() -> bytes:
    df = pd.DataFrame([SOLD_DATA_EXAMPLE_ROW], columns=list(SoldDataColumns.REQUIRED))
    return dataframe_to_excel_bytes(df, sheet_name="Sold_Data")
