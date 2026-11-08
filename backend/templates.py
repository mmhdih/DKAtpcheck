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
    columns = [
        names["live_seller_id"], names["live_seller"], names["live_dkp"],
        names["live_dkpc"], names["live_weight"],
    ]
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
    # The product-name column defaults to the same column weight is parsed
    # from (the variant name), so the example value carries both; if the
    # user points it at a separate column, that column gets its own value.
    # dict.fromkeys de-duplicates the header list while keeping its order.
    example_row = {
        names["sold_seller_id"]: "10001",
        names["sold_seller"]: "Sample Seller",
        names["sold_dkp"]: "551306",
        names["sold_dkpc"]: "59916616",
        names["sold_dkp_name"]: "دستبند طلا ۱۸ عیار",
        names["sold_weight_source"]: "دستبند طلا ۱۸ عیار | 0.65 گرم |",
        names["sold_category"]: "زیورآلات",
        names["sold_net_item_fcast"]: 12,
        names["sold_nmv_fcast"]: 450000000,
    }
    columns = list(dict.fromkeys(example_row))
    df = pd.DataFrame([example_row], columns=columns)
    return dataframe_to_excel_bytes(df, sheet_name="Sold_Data")
