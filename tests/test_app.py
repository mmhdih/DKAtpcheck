from io import BytesIO

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app import app

client = TestClient(app)


def _xlsx_bytes(df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)
    return buf.read()


def _live_bytes() -> bytes:
    return _xlsx_bytes(
        pd.DataFrame(
            {
                "Seller_ID": ["S1", "S1"],
                "Seller_Name": ["ACME", "ACME"],
                "DKP": ["D1", "D2"],
                "DKPC": ["D1C1", "D2C1"],
                "Size_Name": [1.0, 2.0],
            }
        )
    )


def _sold_bytes(rows: list[dict] | None = None) -> bytes:
    if rows is None:
        rows = [
            {
                "marketplace_seller_id": "S1",
                "marketplace_seller_name": "ACME",
                "product_id": "D1",
                "product_variant_id": "D1C1",
                "product_variant_name_fa": 1.0,
                "category_name_fa": "زیورآلات",
                "sum_net_item_fcast": 5,
            },
            {
                "marketplace_seller_id": "S1",
                "marketplace_seller_name": "ACME",
                "product_id": "D9",
                "product_variant_id": "D9C1",
                "product_variant_name_fa": 9.0,
                "category_name_fa": "شمش",
                "sum_net_item_fcast": 1,
            },
        ]
    return _xlsx_bytes(pd.DataFrame(rows))


def _calculate(**form_overrides):
    data = {"tolerance_pct": 10}
    data.update(form_overrides)
    return client.post(
        "/api/v1/calculate",
        files={
            "live_file": ("Live_Data.xlsx", _live_bytes()),
            "sold_file": ("Sold_Data.xlsx", _sold_bytes()),
        },
        data=data,
    )


def test_calculate_end_to_end_with_new_schema():
    response = _calculate()
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]
    row = body["summary"][0]
    assert row["seller_id"] == "S1"
    assert row["seller"] == "ACME"
    assert "dkpc_atp_pct_bullion" in row
    assert "dkpc_atp_pct_jewelry" in row
    assert body["meta"]["seller_zip_generated"] is False


def test_sold_data_categories_endpoint_returns_distinct_sorted_values():
    response = client.post(
        "/api/v1/sold-data/categories",
        files={"sold_file": ("Sold_Data.xlsx", _sold_bytes())},
    )
    assert response.status_code == 200
    assert response.json()["categories"] == sorted(["زیورآلات", "شمش"])


def test_calculate_rejects_unknown_tail_badges():
    response = _calculate(tail_badges="XL")
    assert response.status_code == 400


def test_download_seller_zip_400_when_not_generated():
    result_id = _calculate().json()["result_id"]
    response = client.get(f"/api/v1/download/seller-zip/{result_id}")
    assert response.status_code == 400


def test_download_seller_zip_returns_zip_when_generated():
    result_id = _calculate(generate_seller_zip=True).json()["result_id"]
    response = client.get(f"/api/v1/download/seller-zip/{result_id}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"


def test_download_seller_zip_404_for_unknown_result_id():
    response = client.get("/api/v1/download/seller-zip/does-not-exist")
    assert response.status_code == 404


def test_templates_endpoints_return_xlsx():
    for path in ("/api/v1/templates/live-data", "/api/v1/templates/sold-data"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.content
