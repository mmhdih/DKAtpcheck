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

from .field_names import get_field_names
from .utils import dataframe_to_excel_bytes


def build_live_data_template_bytes() -> bytes:
    names = get_field_names()
    columns = [names["live_seller_id"], names["live_seller"], names["live_dkp"], names["live_dkpc"], names["live_weight"]]
    example_row = {
        names["live_seller_id"]: "10001",
        names["live_seller"]: "Sample Seller",
        names["live_dkp"]: "551306",
        names["live_dkpc"]: "59916616",
        names["live_weight"]: "0.65 گرم",
    }
    df = pd.DataFrame([example_row], columns=columns)
    return dataframe_to_excel_bytes(df, sheet_name="Live_Data")


def build_sold_data_template_bytes() -> bytes:
    names = get_field_names()
    columns = [
        names["sold_seller_id"], names["sold_seller"], names["sold_dkp"], names["sold_dkpc"],
        names["sold_weight_source"], names["sold_category"], names["sold_net_item_fcast"],
    ]
    example_row = {
        names["sold_seller_id"]: "10001",
        names["sold_seller"]: "Sample Seller",
        names["sold_dkp"]: "551306",
        names["sold_dkpc"]: "59916616",
        names["sold_weight_source"]: "0.65 گرم",
        names["sold_category"]: "زیورآلات",
        names["sold_net_item_fcast"]: 12,
    }
    df = pd.DataFrame([example_row], columns=columns)
    return dataframe_to_excel_bytes(df, sheet_name="Sold_Data")
