from io import BytesIO

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend import field_names as fn
from backend.app import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _isolated_field_names_settings_file(tmp_path, monkeypatch):
    """Never touch the real user home directory while testing."""
    monkeypatch.setattr(fn, "_SETTINGS_DIR", tmp_path / ".atp_analyzer")
    monkeypatch.setattr(fn, "_SETTINGS_FILE", tmp_path / ".atp_analyzer" / "field_names.json")
    yield


def _xlsx_bytes(df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)
    return buf.read()


def _csv_bytes(df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    df.to_csv(buf, index=False, encoding="utf-8-sig")
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
                "Weight": [1.0, 2.0],
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
                "product_variant_name_fa": "Gold bracelet | 1 گرم |",
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


def test_calculate_accepts_csv_uploads():
    live_df = pd.DataFrame(
        {
            "Seller_ID": ["S1", "S1"],
            "Seller_Name": ["ACME", "ACME"],
            "DKP": ["D1", "D2"],
            "DKPC": ["D1C1", "D2C1"],
            "Weight": [1.0, 2.0],
        }
    )
    sold_df = pd.DataFrame(
        [
            {
                "marketplace_seller_id": "S1",
                "marketplace_seller_name": "ACME",
                "product_id": "D1",
                "product_variant_id": "D1C1",
                "product_variant_name_fa": 1.0,
                "category_name_fa": "زیورآلات",
                "sum_net_item_fcast": 5,
            }
        ]
    )
    response = client.post(
        "/api/v1/calculate",
        files={
            "live_file": ("Live_Data.csv", _csv_bytes(live_df)),
            "sold_file": ("Sold_Data.csv", _csv_bytes(sold_df)),
        },
        data={"tolerance_pct": 10},
    )
    assert response.status_code == 200
    assert response.json()["summary"][0]["seller_id"] == "S1"


def test_calculate_response_includes_tail_summary_with_correct_counts():
    # D1/D1C1 exists in Live_Data (ATP); D_X/D_XC1 and D_Y/D_YC1 don't (not ATP).
    sold_rows = [
        {
            "marketplace_seller_id": "S1", "marketplace_seller_name": "ACME",
            "product_id": "D1", "product_variant_id": "D1C1",
            "product_variant_name_fa": 1.0, "category_name_fa": "",
            "sum_net_item_fcast": 30,
        },
        {
            "marketplace_seller_id": "S1", "marketplace_seller_name": "ACME",
            "product_id": "D_X", "product_variant_id": "D_XC1",
            "product_variant_name_fa": 1.0, "category_name_fa": "",
            "sum_net_item_fcast": 40,
        },
        {
            "marketplace_seller_id": "S1", "marketplace_seller_name": "ACME",
            "product_id": "D_Y", "product_variant_id": "D_YC1",
            "product_variant_name_fa": 1.0, "category_name_fa": "",
            "sum_net_item_fcast": 30,
        },
    ]
    response = client.post(
        "/api/v1/calculate",
        files={
            "live_file": ("Live_Data.xlsx", _live_bytes()),
            "sold_file": ("Sold_Data.xlsx", _xlsx_bytes(pd.DataFrame(sold_rows))),
        },
        data={"tolerance_pct": 10},
    )
    assert response.status_code == 200
    body = response.json()
    # Total 100. D_X (40) is the top item with nothing above it -> ST;
    # D1 (30) starts at 40% -> MT; D_Y (30) starts at 70% -> LT.
    assert len(body["tail_summary"]) == 1
    row = body["tail_summary"][0]
    assert row["seller_id"] == "S1"
    assert row["st_unavailable"] == 1  # D_X: ST badge, NOT ATP
    assert row["mt_available"] == 1  # D1: MT badge, ATP
    assert row["lt_unavailable"] == 1  # D_Y: LT badge, NOT ATP
    assert row["st_available"] == 0
    assert row["mt_unavailable"] == 0
    assert row["lt_available"] == 0

    dl = client.get(f"/api/v1/download/tail-summary/{body['result_id']}")
    assert dl.status_code == 200
    assert dl.content

    dl_list = client.get(f"/api/v1/download/tail-dkp-list/{body['result_id']}")
    assert dl_list.status_code == 200
    assert dl_list.content


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


def test_calculate_response_includes_seller_tail_summary():
    # Same fixture as test_calculate_response_includes_tail_summary_with_correct_counts,
    # just asserting the standalone per-seller-ranked tab's field is populated too
    # (its own classification math is covered in tests/test_tail_classifier.py).
    sold_rows = [
        {
            "marketplace_seller_id": "S1", "marketplace_seller_name": "ACME",
            "product_id": "D1", "product_variant_id": "D1C1",
            "product_variant_name_fa": 1.0, "category_name_fa": "",
            "sum_net_item_fcast": 30,
        },
        {
            "marketplace_seller_id": "S1", "marketplace_seller_name": "ACME",
            "product_id": "D_X", "product_variant_id": "D_XC1",
            "product_variant_name_fa": 1.0, "category_name_fa": "",
            "sum_net_item_fcast": 40,
        },
    ]
    response = client.post(
        "/api/v1/calculate",
        files={
            "live_file": ("Live_Data.xlsx", _live_bytes()),
            "sold_file": ("Sold_Data.xlsx", _xlsx_bytes(pd.DataFrame(sold_rows))),
        },
        data={"tolerance_pct": 10},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["seller_tail_summary"]) == 1
    row = body["seller_tail_summary"][0]
    assert row["seller_id"] == "S1"
    # D1 (30) + D_X (40) = 70 total for this seller alone. D_X sorts first
    # with nothing above it -> ST (and it's NOT ATP); D1 then starts at
    # 40/70 = 57.1% -> MT (and it IS ATP). The badges are computed against
    # this seller's OWN 70 total, not the marketplace grand total.
    assert row["st_unavailable"] == 1
    assert row["mt_available"] == 1
    assert row["st_available"] == 0
    assert row["mt_unavailable"] == 0
    assert row["lt_available"] == 0
    assert row["lt_unavailable"] == 0

    dl_summary = client.get(f"/api/v1/download/seller-tail-summary/{body['result_id']}")
    assert dl_summary.status_code == 200
    assert dl_summary.content

    dl_list = client.get(f"/api/v1/download/seller-tail-dkp-list/{body['result_id']}")
    assert dl_list.status_code == 200
    assert dl_list.content


def test_download_seller_tail_zip_400_when_not_generated():
    result_id = _calculate().json()["result_id"]
    response = client.get(f"/api/v1/download/seller-tail-zip/{result_id}")
    assert response.status_code == 400


def test_download_seller_tail_zip_returns_zip_when_generated():
    result_id = _calculate(generate_seller_tail_zip=True).json()["result_id"]
    response = client.get(f"/api/v1/download/seller-tail-zip/{result_id}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"


def test_download_seller_tail_zip_404_for_unknown_result_id():
    response = client.get("/api/v1/download/seller-tail-zip/does-not-exist")
    assert response.status_code == 404


def test_templates_endpoints_return_xlsx():
    for path in ("/api/v1/templates/live-data", "/api/v1/templates/sold-data"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.content


def test_missing_preview_lists_both_statuses_with_badge_and_product_name():
    body = _calculate().json()
    rows = {row["dkpc"]: row for row in body["missing_preview"]}
    # D1C1 is live in Live_Data; D9C1 is not.
    assert rows["D1C1"]["status"] == "Available"
    assert rows["D9C1"]["status"] == "Unavailable"
    # Names come from Sold_Data's name column (product_variant_name_fa by default).
    assert rows["D1C1"]["dkp_name"] == "Gold bracelet | 1 گرم |"
    assert rows["D9C1"]["dkp_name"] == "9"
    assert rows["D1C1"]["tail_badge"] in {"ST", "MT", "LT"}
    assert body["missing_total_count"] == 2
    assert body["missing_unavailable_count"] == 1


def test_missing_excludes_dkpcs_with_no_forecast_volume():
    sold_rows = [
        {
            "marketplace_seller_id": "S1", "marketplace_seller_name": "ACME",
            "product_id": "D1", "product_variant_id": "D1C1",
            "product_variant_name_fa": 1.0, "category_name_fa": "",
            "sum_net_item_fcast": 5,
        },
        {
            "marketplace_seller_id": "S1", "marketplace_seller_name": "ACME",
            "product_id": "D2", "product_variant_id": "D2C1",
            "product_variant_name_fa": 2.0, "category_name_fa": "",
            "sum_net_item_fcast": 0,
        },
    ]
    response = client.post(
        "/api/v1/calculate",
        files={
            "live_file": ("Live_Data.xlsx", _live_bytes()),
            "sold_file": ("Sold_Data.xlsx", _xlsx_bytes(pd.DataFrame(sold_rows))),
        },
        data={"tolerance_pct": 10},
    )
    assert response.status_code == 200
    listed = [row["dkpc"] for row in response.json()["missing_preview"]]
    assert listed == ["D1C1"]


def test_missing_uses_the_per_seller_badge_not_the_marketplace_one():
    # (S1,D1)=10, (S2,DBIG)=100, (S2,DSMALL)=1 in one bucket. Marketplace-wide
    # S1's DKP sits at 90% of accumulated volume -> LT; ranked within S1's own
    # sales it is their only item -> ST. The Missing tab must show ST.
    sold_rows = [
        {
            "marketplace_seller_id": "S1", "marketplace_seller_name": "ACME",
            "product_id": "D1", "product_variant_id": "D1C1",
            "product_variant_name_fa": 1.0, "category_name_fa": "",
            "sum_net_item_fcast": 10,
        },
        {
            "marketplace_seller_id": "S2", "marketplace_seller_name": "Beta",
            "product_id": "DBIG", "product_variant_id": "DBIGC1",
            "product_variant_name_fa": 1.0, "category_name_fa": "",
            "sum_net_item_fcast": 100,
        },
        {
            "marketplace_seller_id": "S2", "marketplace_seller_name": "Beta",
            "product_id": "DSMALL", "product_variant_id": "DSMALLC1",
            "product_variant_name_fa": 1.0, "category_name_fa": "",
            "sum_net_item_fcast": 1,
        },
    ]
    response = client.post(
        "/api/v1/calculate",
        files={
            "live_file": ("Live_Data.xlsx", _live_bytes()),
            "sold_file": ("Sold_Data.xlsx", _xlsx_bytes(pd.DataFrame(sold_rows))),
        },
        data={"tolerance_pct": 10},
    )
    assert response.status_code == 200
    body = response.json()

    s1_row = next(row for row in body["missing_preview"] if row["seller_id"] == "S1")
    assert s1_row["tail_badge"] == "ST"

    # Same seller, same DKP, marketplace-wide ranking: LT (and available,
    # since S1/D1 is live) — proving the two tabs really do rank differently.
    s1_marketplace = next(row for row in body["tail_summary"] if row["seller_id"] == "S1")
    assert s1_marketplace["lt_available"] == 1
    assert s1_marketplace["st_available"] == 0


def test_get_field_names_returns_defaults():
    response = client.get("/api/v1/field-names")
    assert response.status_code == 200
    fields = {f["key"]: f for f in response.json()["fields"]}
    assert fields["live_weight"]["value"] == fields["live_weight"]["default"] == "Weight"


def test_update_field_names_persists_and_is_reflected_in_get():
    response = client.post("/api/v1/field-names", json={"values": {"live_weight": "Renamed"}})
    assert response.status_code == 200
    fields = {f["key"]: f for f in response.json()["fields"]}
    assert fields["live_weight"]["value"] == "Renamed"

    response = client.get("/api/v1/field-names")
    fields = {f["key"]: f for f in response.json()["fields"]}
    assert fields["live_weight"]["value"] == "Renamed"


def test_update_field_names_rejects_unknown_key():
    response = client.post("/api/v1/field-names", json={"values": {"not_a_real_key": "x"}})
    assert response.status_code == 400


def test_reset_field_names_reverts_to_default():
    client.post("/api/v1/field-names", json={"values": {"live_weight": "Renamed"}})
    response = client.post("/api/v1/field-names/reset")
    assert response.status_code == 200
    fields = {f["key"]: f for f in response.json()["fields"]}
    assert fields["live_weight"]["value"] == "Weight"


def test_calculate_uses_renamed_live_weight_column():
    client.post("/api/v1/field-names", json={"values": {"live_weight": "Renamed_Weight"}})
    live_bytes = _xlsx_bytes(
        pd.DataFrame(
            {
                "Seller_ID": ["S1", "S1"],
                "Seller_Name": ["ACME", "ACME"],
                "DKP": ["D1", "D2"],
                "DKPC": ["D1C1", "D2C1"],
                "Renamed_Weight": [1.0, 2.0],
            }
        )
    )
    response = client.post(
        "/api/v1/calculate",
        files={
            "live_file": ("Live_Data.xlsx", live_bytes),
            "sold_file": ("Sold_Data.xlsx", _sold_bytes()),
        },
        data={"tolerance_pct": 10},
    )
    assert response.status_code == 200
    assert response.json()["summary"][0]["seller_id"] == "S1"


def _metric_sold_rows() -> list[dict]:
    # Same seller/bucket, two DKPs whose order flips between the metrics:
    # by net items D1 dominates (90 vs 10), by NMV D2 does (10 vs 990).
    common = {
        "marketplace_seller_id": "S1", "marketplace_seller_name": "ACME",
        "product_variant_name_fa": 1.0, "category_name_fa": "",
    }
    return [
        {**common, "product_id": "D1", "product_variant_id": "D1C1",
         "sum_net_item_fcast": 90, "sum_nmv_fcast": 10},
        {**common, "product_id": "D2", "product_variant_id": "D2C1",
         "sum_net_item_fcast": 10, "sum_nmv_fcast": 990},
    ]


def _calculate_with_sold(rows: list[dict], **form):
    return client.post(
        "/api/v1/calculate",
        files={
            "live_file": ("Live_Data.xlsx", _live_bytes()),
            "sold_file": ("Sold_Data.xlsx", _xlsx_bytes(pd.DataFrame(rows))),
        },
        data={"tolerance_pct": 10, **form},
    )


def _badges_by_dkp(body: dict) -> dict[str, str]:
    return {row["dkp"]: row["tail_badge"] for row in body["missing_preview"]}


def test_calculate_defaults_to_net_item_ranking():
    response = _calculate_with_sold(_metric_sold_rows())
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["volume_metric"] == "net_item"
    assert _badges_by_dkp(body) == {"D1": "ST", "D2": "LT"}


def test_calculate_ranks_by_nmv_when_selected():
    response = _calculate_with_sold(_metric_sold_rows(), volume_metric="nmv")
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["volume_metric"] == "nmv"
    assert _badges_by_dkp(body) == {"D1": "LT", "D2": "ST"}


def test_calculate_nmv_without_nmv_column_returns_400():
    rows = [{k: v for k, v in row.items() if k != "sum_nmv_fcast"} for row in _metric_sold_rows()]
    response = _calculate_with_sold(rows, volume_metric="nmv")
    assert response.status_code == 400
    assert "sum_nmv_fcast" in response.json()["detail"]


def test_calculate_rejects_unknown_volume_metric():
    response = _calculate_with_sold(_metric_sold_rows(), volume_metric="gmv")
    assert response.status_code == 400


def test_categories_endpoint_needs_no_volume_column():
    rows = [
        {k: v for k, v in row.items() if k not in ("sum_net_item_fcast", "sum_nmv_fcast")}
        for row in _metric_sold_rows()
    ]
    response = client.post(
        "/api/v1/sold-data/categories",
        files={"sold_file": ("Sold_Data.xlsx", _xlsx_bytes(pd.DataFrame(rows)))},
    )
    assert response.status_code == 200


def test_config_advertises_volume_metrics():
    body = client.get("/api/v1/config").json()
    assert [m["key"] for m in body["volume_metrics"]] == ["net_item", "nmv"]
    assert body["default_volume_metric"] == "net_item"


def test_bullion_defaults_get_save_reset_roundtrip():
    body = client.get("/api/v1/bullion-defaults").json()
    assert body["categories"] == body["builtin_default"]
    assert "شمش طلا" in body["categories"]

    body = client.post("/api/v1/bullion-defaults", json={"categories": ["سکه بهار آزادی"]}).json()
    assert body["categories"] == ["سکه بهار آزادی"]
    assert client.get("/api/v1/bullion-defaults").json()["categories"] == ["سکه بهار آزادی"]

    body = client.post("/api/v1/bullion-defaults/reset").json()
    assert body["categories"] == body["builtin_default"]


def test_categories_endpoint_reports_available_volume_metrics():
    rows = [{k: v for k, v in row.items() if k != "sum_nmv_fcast"} for row in _metric_sold_rows()]
    response = client.post(
        "/api/v1/sold-data/categories",
        files={"sold_file": ("Sold_Data.xlsx", _xlsx_bytes(pd.DataFrame(rows)))},
    )
    assert response.json()["available_volume_metrics"] == ["net_item"]

    response = client.post(
        "/api/v1/sold-data/categories",
        files={"sold_file": ("Sold_Data.xlsx", _xlsx_bytes(pd.DataFrame(_metric_sold_rows())))},
    )
    assert response.json()["available_volume_metrics"] == ["net_item", "nmv"]


def test_missing_nmv_error_suggests_switching_to_net_item():
    rows = [{k: v for k, v in row.items() if k != "sum_nmv_fcast"} for row in _metric_sold_rows()]
    detail = _calculate_with_sold(rows, volume_metric="nmv").json()["detail"]
    assert "switch the ranking metric to Net item" in detail
    assert "تنظیمات" in detail
