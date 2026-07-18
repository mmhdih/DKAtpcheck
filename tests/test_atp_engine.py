import numpy as np
import pandas as pd
import pytest

from backend.atp_engine import ATPEngine, ATPIndex
from backend.config import CanonicalColumns as C
from backend.models import ATPMatchType


def _live(rows: list[tuple[str, str, str, float | None]]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=[C.SELLER, C.DKP, C.DKPC, C.WEIGHT])
    df[C.SELLER_KEY] = df[C.SELLER].str.casefold()
    return df


def _sold(rows: list[tuple[str, str, str, float | None]]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=[C.SELLER, C.DKP, C.DKPC, C.WEIGHT])
    df[C.SELLER_KEY] = df[C.SELLER].str.casefold()
    return df


@pytest.fixture
def live_df():
    return _live(
        [
            ("ACME", "D1", "D1C1", 0.65),
            ("ACME", "D1", "D1C2", 1.0),
            ("ACME", "D4", "D4C1", 3.25),
            ("Beta Co", "D2", "D2C1", 2.5),
            ("Gamma", "D3", "D3C1", np.nan),
        ]
    )


@pytest.fixture
def index(live_df):
    return ATPIndex.build(live_df)


def test_exact_dkpc_match(index):
    sold = _sold([("ACME", "D1", "D1C1", 0.65)])
    result = ATPEngine(index=index, tolerance_pct=0).compute(sold)
    row = result.dkpc_results.iloc[0]
    assert row["is_atp"]
    assert row["match_type"] == ATPMatchType.EXACT_DKPC


def test_zero_tolerance_rejects_close_but_not_exact_weight(index):
    sold = _sold([("ACME", "D1", "D1C9", 0.68)])  # not an exact DKPC, weight close to 0.65
    result = ATPEngine(index=index, tolerance_pct=0).compute(sold)
    row = result.dkpc_results.iloc[0]
    assert not row["is_atp"]
    assert row["match_type"] == ATPMatchType.NOT_ATP


def test_tolerance_allows_close_weight(index):
    sold = _sold([("ACME", "D1", "D1C9", 0.68)])  # within 5% of 0.65
    result = ATPEngine(index=index, tolerance_pct=5).compute(sold)
    row = result.dkpc_results.iloc[0]
    assert row["is_atp"]
    assert row["match_type"] == ATPMatchType.WEIGHT_TOLERANCE


def test_tolerance_rejects_far_weight(index):
    sold = _sold([("ACME", "D1", "D1C9", 10.0)])  # nowhere near any ACME live weight
    result = ATPEngine(index=index, tolerance_pct=20).compute(sold)
    row = result.dkpc_results.iloc[0]
    assert not row["is_atp"]


def test_unresolvable_sold_weight_is_exact_match_only(index):
    # Not an exact DKPC and no sold weight -> must NOT fall back to tolerance search.
    sold = _sold([("ACME", "D1", "UNKNOWN", np.nan)])
    result = ATPEngine(index=index, tolerance_pct=50).compute(sold)
    row = result.dkpc_results.iloc[0]
    assert not row["is_atp"]


def test_exact_match_wins_even_with_nan_live_weight(index):
    # Gamma's only live DKPC has an unresolvable weight, but exact DKPC match
    # must still succeed regardless of weight resolution on either side.
    sold = _sold([("Gamma", "D3", "D3C1", np.nan)])
    result = ATPEngine(index=index, tolerance_pct=0).compute(sold)
    row = result.dkpc_results.iloc[0]
    assert row["is_atp"]
    assert row["match_type"] == ATPMatchType.EXACT_DKPC


def test_dkp_level_atp_is_weight_independent(index):
    # DKP D1 exists live for ACME; sold DKPC doesn't matter for DKP-level check.
    sold = _sold([("ACME", "D1", "SOME_OTHER_DKPC", 999.0)])
    result = ATPEngine(index=index, tolerance_pct=0).compute(sold)
    dkp_row = result.dkp_results.iloc[0]
    assert dkp_row["is_atp"]


def test_dkp_level_false_when_seller_has_no_such_dkp(index):
    sold = _sold([("ACME", "D999", "X", None)])
    result = ATPEngine(index=index, tolerance_pct=0).compute(sold)
    dkp_row = result.dkp_results.iloc[0]
    assert not dkp_row["is_atp"]


def test_unknown_seller_never_matches(index):
    sold = _sold([("Unknown Seller", "D1", "D1C1", 0.65)])
    result = ATPEngine(index=index, tolerance_pct=100).compute(sold)
    assert not result.dkpc_results.iloc[0]["is_atp"]
    assert not result.dkp_results.iloc[0]["is_atp"]


def test_repeated_sales_of_same_dkpc_count_once(index):
    # Same (seller, dkpc) sold 3 times -> exactly one row in the result.
    sold = _sold(
        [
            ("ACME", "D1", "D1C1", 0.65),
            ("ACME", "D1", "D1C1", 0.65),
            ("ACME", "D1", "D1C1", 0.65),
        ]
    )
    result = ATPEngine(index=index, tolerance_pct=0).compute(sold)
    assert len(result.dkpc_results) == 1
    assert len(result.dkp_results) == 1


def test_repeated_sales_of_same_dkp_across_different_dkpc_count_once(index):
    sold = _sold(
        [
            ("ACME", "D1", "D1C1", 0.65),
            ("ACME", "D1", "D1C2", 1.0),
        ]
    )
    result = ATPEngine(index=index, tolerance_pct=0).compute(sold)
    assert len(result.dkpc_results) == 2  # two distinct DKPCs
    assert len(result.dkp_results) == 1  # but one distinct DKP
