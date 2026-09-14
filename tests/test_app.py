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
                "DKP Name": ["Gold bracelet", "Silver ring"],
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
    assert rows["D1C1"]["dkp_name"] == "Gold bracelet"
    # D9 is nowhere in Live_Data, so its name can't be resolved.
    assert rows["D9C1"]["dkp_name"] == ""
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


def test_warns_when_no_sold_dkp_resolves_a_product_name():
    # Live_Data carries names, but for other products entirely — the name
    # column would silently come out blank, so the run has to say why.
    sold_rows = [
        {
            "marketplace_seller_id": "S1", "marketplace_seller_name": "ACME",
            "product_id": "D_NOT_LIVE", "product_variant_id": "D_NOT_LIVE_C1",
            "product_variant_name_fa": 1.0, "category_name_fa": "",
            "sum_net_item_fcast": 5,
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
    assert any("DKP Name is blank" in w for w in response.json()["meta"]["warnings"])


def test_calculate_resolves_product_names_from_a_differently_cased_header():
    live_bytes = _xlsx_bytes(
        pd.DataFrame(
            {
                "Seller_ID": ["S1"],
                "Seller_Name": ["ACME"],
                "DKP": ["D1"],
                "DKP_NAME": ["Gold bracelet"],  # underscore + caps, not "DKP Name"
                "DKPC": ["D1C1"],
                "Weight": [1.0],
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
    body = response.json()
    row = next(r for r in body["missing_preview"] if r["dkpc"] == "D1C1")
    assert row["dkp_name"] == "Gold bracelet"
