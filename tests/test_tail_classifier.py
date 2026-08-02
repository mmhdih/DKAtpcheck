import numpy as np
import pandas as pd
import pytest

from backend.config import CanonicalColumns as C
from backend.config import CategoryBucket
from backend.config import TailClassification
from backend.tail_classifier import classify_tails


def _sold_totals(
    rows: list[tuple[str, str, float | None]], *, bucket: str = CategoryBucket.JEWELRY
) -> pd.DataFrame:
    """rows: (seller_key, dkp, net_item_fcast) — one row per sold DKPC, all in the same bucket."""
    df = pd.DataFrame(rows, columns=[C.SELLER_KEY, C.DKP, C.NET_ITEM_FCAST])
    df[C.BUCKET] = bucket
    return df


def _badge_for(result: pd.DataFrame, seller_key: str, dkp: str) -> str | None:
    match = result[(result[C.SELLER_KEY] == seller_key) & (result[C.DKP] == dkp)]
    return match[C.TAIL_BADGE].iloc[0] if len(match) else None


def test_ranking_is_global_across_all_sellers():
    # Seller "a" and seller "b" each have a dominant DKP of EQUAL volume
    # (99), both in the same bucket. If ranking were done separately per
    # seller, both would be symmetric and land in the same bucket. Ranked
    # GLOBALLY (one shared cumulative curve across every seller combined),
    # seller "a"'s DKP2 sorts first (stable tie-break preserves original
    # order) and lands at 49.5% cumulative (MT), while seller "b"'s DKP4
    # only reaches the curve after DKP2 is already counted, landing at 99%
    # (LT) — proving the denominator/ordering is the grand total, not each
    # seller's own.
    sold = _sold_totals(
        [
            ("a", "D1", 1.0),
            ("a", "D2", 99.0),
            ("b", "D3", 1.0),
            ("b", "D4", 99.0),
        ]
    )
    result = classify_tails(sold)
    assert _badge_for(result, "a", "D2") == TailClassification.MT
    assert _badge_for(result, "b", "D4") == TailClassification.LT


def test_ranking_is_independent_per_bucket():
    # Bullion's volume must have NO effect on how Jewelry's own DKPs are
    # ranked against each other, and vice versa — each bucket forms its
    # own independent Pareto curve. Within Bullion alone (total 100):
    # D_BULLION is the unambiguous largest single item (25, no ties, so
    # groupby's internal alphabetical pre-sort can't affect tie-breaking)
    # and ranks first, cum=25% -> ST.
    bullion = _sold_totals(
        [("s", "D_BULLION", 25.0), ("s", "DB2", 20.0), ("s", "DB3", 20.0), ("s", "DB4", 20.0), ("s", "DB5", 15.0)],
        bucket=CategoryBucket.BULLION,
    )
    # Within Jewelry alone: D2 (40, largest) cum=40% -> MT; D1 (30) cum=70% -> MT; D3 (30) cum=100% -> LT.
    jewelry = _sold_totals(
        [("s", "D1", 30.0), ("s", "D2", 40.0), ("s", "D3", 30.0)], bucket=CategoryBucket.JEWELRY
    )
    sold = pd.concat([bullion, jewelry], ignore_index=True)
    result = classify_tails(sold)

    assert _badge_for(result, "s", "D_BULLION") == TailClassification.ST
    assert _badge_for(result, "s", "D2") == TailClassification.MT
    assert _badge_for(result, "s", "D1") == TailClassification.MT
    assert _badge_for(result, "s", "D3") == TailClassification.LT


def test_st_cutoff_is_inclusive_at_30():
    # Grand total = 100. Largest item (30) ranks first with cumulative
    # exactly 30% -> ST (boundary inclusive, not exclusive).
    sold = _sold_totals([("s", "D1", 30.0), ("s", "D2", 25.0), ("s", "D3", 25.0), ("s", "D4", 20.0)])
    result = classify_tails(sold)
    assert _badge_for(result, "s", "D1") == TailClassification.ST


def test_mt_cutoff_is_inclusive_at_70():
    # Grand total = 100. Largest item (70) ranks first with cumulative
    # exactly 70% -> MT (boundary inclusive, not LT).
    sold = _sold_totals([("s", "D1", 70.0), ("s", "D2", 30.0)])
    result = classify_tails(sold)
    assert _badge_for(result, "s", "D1") == TailClassification.MT
    assert _badge_for(result, "s", "D2") == TailClassification.LT


def test_zero_or_all_nan_net_item_fcast_pairs_are_excluded_entirely():
    sold = _sold_totals(
        [
            ("s", "D_ZERO", 0.0),
            ("s", "D_NAN", np.nan),
            ("s", "D_REAL", 10.0),
        ]
    )
    result = classify_tails(sold)
    assert _badge_for(result, "s", "D_ZERO") is None
    assert _badge_for(result, "s", "D_NAN") is None
    assert _badge_for(result, "s", "D_REAL") is not None


def test_partial_nan_rows_still_sum_the_real_values():
    sold = _sold_totals(
        [
            ("s", "D1", 10.0),
            ("s", "D1", np.nan),
            ("s", "D1", 5.0),
        ]
    )
    result = classify_tails(sold)
    # 10 + 5 = 15, NaN row contributes nothing but doesn't zero out the group.
    assert _badge_for(result, "s", "D1") is not None


def test_returns_seller_dkp_granularity_not_dkpc():
    sold = _sold_totals([("s", "D1", 10.0), ("s", "D1", 20.0)])
    result = classify_tails(sold)
    assert len(result) == 1
    assert set(result.columns) == {C.SELLER_KEY, C.DKP, C.TAIL_BADGE}


def test_empty_input_returns_empty_frame():
    sold = _sold_totals([])
    result = classify_tails(sold)
    assert result.empty
    assert set(result.columns) == {C.SELLER_KEY, C.DKP, C.TAIL_BADGE}
