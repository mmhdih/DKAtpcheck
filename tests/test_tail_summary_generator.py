import pandas as pd
import pytest

from backend.atp_engine import ATPResult
from backend.config import CanonicalColumns as C
from backend.config import TailClassification
from backend.tail_summary_generator import build_tail_summary


def _dkp_row(seller_id, seller, badge, is_atp) -> dict:
    return {
        C.SELLER_ID: seller_id,
        C.SELLER: seller,
        C.SELLER_KEY: seller_id.casefold(),
        C.TAIL_BADGE: badge,
        "is_atp": is_atp,
    }


_DKP_COLUMNS = [C.SELLER_ID, C.SELLER, C.SELLER_KEY, C.TAIL_BADGE, "is_atp"]


def _result(dkp_rows: list[dict]) -> ATPResult:
    dkp_df = pd.DataFrame(dkp_rows, columns=_DKP_COLUMNS) if dkp_rows else pd.DataFrame(columns=_DKP_COLUMNS)
    return ATPResult(dkpc_results=pd.DataFrame(), dkp_results=dkp_df)


def test_counts_available_and_unavailable_per_badge():
    rows = [
        _dkp_row("S1", "ACME", TailClassification.ST, True),
        _dkp_row("S1", "ACME", TailClassification.ST, True),
        _dkp_row("S1", "ACME", TailClassification.ST, False),
        _dkp_row("S1", "ACME", TailClassification.MT, False),
        _dkp_row("S1", "ACME", TailClassification.LT, True),
    ]
    result = _result(rows)
    tail_summary = build_tail_summary(result)
    row = tail_summary.iloc[0]
    assert row["ST Available"] == 2
    assert row["ST Unavailable"] == 1
    assert row["MT Available"] == 0
    assert row["MT Unavailable"] == 1
    assert row["LT Available"] == 1
    assert row["LT Unavailable"] == 0


def test_includes_seller_id_and_seller_columns():
    rows = [_dkp_row("S1", "ACME", TailClassification.ST, True)]
    tail_summary = build_tail_summary(_result(rows))
    assert list(tail_summary.columns)[:2] == ["Seller ID", "Seller"]
    assert tail_summary.iloc[0]["Seller ID"] == "S1"
    assert tail_summary.iloc[0]["Seller"] == "ACME"


def test_unbadged_dkps_are_excluded_from_counts():
    rows = [
        _dkp_row("S1", "ACME", TailClassification.ST, True),
        _dkp_row("S1", "ACME", None, True),  # no badge (zero/blank net_item_fcast)
    ]
    tail_summary = build_tail_summary(_result(rows))
    row = tail_summary.iloc[0]
    assert row["ST Available"] == 1
    assert row[["ST Available", "ST Unavailable", "MT Available", "MT Unavailable", "LT Available", "LT Unavailable"]].sum() == 1


def test_seller_with_no_badged_dkps_is_omitted():
    rows = [
        _dkp_row("S1", "ACME", TailClassification.ST, True),
        _dkp_row("S2", "Beta", None, True),
    ]
    tail_summary = build_tail_summary(_result(rows))
    assert list(tail_summary["Seller ID"]) == ["S1"]


def test_empty_result_returns_empty_frame_with_expected_columns():
    tail_summary = build_tail_summary(_result([]))
    assert tail_summary.empty
    assert list(tail_summary.columns) == [
        "Seller ID", "Seller",
        "ST Available", "ST Unavailable",
        "MT Available", "MT Unavailable",
        "LT Available", "LT Unavailable",
    ]


def test_counts_are_ints_not_floats():
    rows = [_dkp_row("S1", "ACME", TailClassification.ST, True)]
    tail_summary = build_tail_summary(_result(rows))
    assert tail_summary["ST Available"].dtype.kind == "i"
