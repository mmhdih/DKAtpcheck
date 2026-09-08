import pandas as pd
import pytest

from backend.atp_engine import ATPResult
from backend.config import CanonicalColumns as C
from backend.config import CategoryBucket
from backend.missing_generator import OUTPUT_COLUMNS, build_missing


def _row(dkpc, is_atp, **overrides) -> dict:
    row = {
        C.SELLER_ID: "S1",
        C.SELLER: "ACME",
        C.DKP: "D1",
        C.DKP_NAME: "Gold bracelet",
        C.DKPC: dkpc,
        C.CATEGORY: "زیورآلات",
        C.BUCKET: CategoryBucket.JEWELRY,
        C.TAIL_BADGE: "ST",
        "is_atp": is_atp,
    }
    row.update(overrides)
    return row


def _result(rows: list[dict]) -> ATPResult:
    return ATPResult(dkpc_results=pd.DataFrame(rows), dkp_results=pd.DataFrame())


def test_missing_lists_both_statuses_with_a_status_column():
    missing = build_missing(_result([_row("D1C1", is_atp=False), _row("D1C2", is_atp=True)]))
    assert dict(zip(missing["DKPC"], missing["Status"])) == {
        "D1C1": "Unavailable",
        "D1C2": "Available",
    }


def test_missing_puts_unavailable_rows_first():
    missing = build_missing(_result([_row("LIVE", is_atp=True), _row("GONE", is_atp=False)]))
    assert list(missing["DKPC"]) == ["GONE", "LIVE"]


def test_missing_sorts_by_badge_priority_within_a_status():
    rows = [
        _row("LT_ROW", is_atp=False, **{C.TAIL_BADGE: "LT"}),
        _row("ST_ROW", is_atp=False, **{C.TAIL_BADGE: "ST"}),
        _row("MT_ROW", is_atp=False, **{C.TAIL_BADGE: "MT"}),
    ]
    missing = build_missing(_result(rows))
    assert list(missing["DKPC"]) == ["ST_ROW", "MT_ROW", "LT_ROW"]


def test_missing_excludes_unbadged_dkpcs():
    # Same identification rule as the Per-Seller Item-Tail report: a DKP
    # with no badge (zero/blank forecast volume) is not listed at all.
    rows = [_row("BADGED", is_atp=False), _row("UNBADGED", is_atp=False, **{C.TAIL_BADGE: None})]
    missing = build_missing(_result(rows))
    assert list(missing["DKPC"]) == ["BADGED"]


def test_missing_is_empty_when_nothing_is_badged():
    missing = build_missing(_result([_row("D1C1", is_atp=False, **{C.TAIL_BADGE: None})]))
    assert missing.empty
    assert list(missing.columns) == OUTPUT_COLUMNS


def test_missing_includes_seller_id_dkp_name_category_and_bucket():
    rows = [
        _row(
            "D1C1", is_atp=False,
            **{C.CATEGORY: "شمش", C.BUCKET: CategoryBucket.BULLION, C.DKP_NAME: "شمش طلا ۱ گرمی"},
        )
    ]
    missing = build_missing(_result(rows))
    row = missing.iloc[0]
    assert row["Seller ID"] == "S1"
    assert row["DKP Name"] == "شمش طلا ۱ گرمی"
    assert row["Category"] == "شمش"
    assert row["Bucket"] == CategoryBucket.BULLION


def test_missing_output_columns_are_exactly_the_expected_set():
    missing = build_missing(_result([_row("D1C1", is_atp=False)]))
    assert list(missing.columns) == [
        "Seller ID", "Seller", "DKP", "DKP Name", "DKPC",
        "Category", "Bucket", "Tail Badge", "Status",
    ]
