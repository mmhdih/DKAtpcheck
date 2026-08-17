import numpy as np
import pandas as pd
import pytest

from backend.config import CanonicalColumns as C
from backend.config import CategoryBucket
from backend.config import TailClassification
from backend.tail_classifier import classify_tails, classify_tails_per_seller


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
    # seller, both would be symmetric and land in the same band. Ranked
    # GLOBALLY (one shared cumulative curve across every seller combined),
    # seller "a"'s DKP2 sorts first (stable tie-break preserves original
    # order) with nothing accumulated above it (ST), while seller "b"'s
    # DKP4 only reaches the curve after DKP2 is already counted, starting
    # at 49.5% (MT) — proving the denominator/ordering is the grand total,
    # not each seller's own.
    sold = _sold_totals(
        [
            ("a", "D1", 1.0),
            ("a", "D2", 99.0),
            ("b", "D3", 1.0),
            ("b", "D4", 99.0),
        ]
    )
    result = classify_tails(sold)
    assert _badge_for(result, "a", "D2") == TailClassification.ST
    assert _badge_for(result, "b", "D4") == TailClassification.MT


def test_ranking_is_independent_per_bucket():
    # Bullion's volume must have NO effect on how Jewelry's own DKPs are
    # ranked against each other, and vice versa — each bucket forms its
    # own independent Pareto curve. Within Bullion alone (total 100):
    # D_BULLION is the unambiguous largest single item (25, no ties, so
    # groupby's internal alphabetical pre-sort can't affect tie-breaking)
    # and ranks first with 0% above it -> ST.
    bullion = _sold_totals(
        [("s", "D_BULLION", 25.0), ("s", "DB2", 20.0), ("s", "DB3", 20.0), ("s", "DB4", 20.0), ("s", "DB5", 15.0)],
        bucket=CategoryBucket.BULLION,
    )
    # Within Jewelry alone: D2 (40, largest) starts at 0% -> ST; D1 (30)
    # starts at 40% -> MT; D3 (30) starts at 70% -> LT.
    jewelry = _sold_totals(
        [("s", "D1", 30.0), ("s", "D2", 40.0), ("s", "D3", 30.0)], bucket=CategoryBucket.JEWELRY
    )
    sold = pd.concat([bullion, jewelry], ignore_index=True)
    result = classify_tails(sold)

    assert _badge_for(result, "s", "D_BULLION") == TailClassification.ST
    assert _badge_for(result, "s", "D2") == TailClassification.ST
    assert _badge_for(result, "s", "D1") == TailClassification.MT
    assert _badge_for(result, "s", "D3") == TailClassification.LT


def test_st_band_ends_at_30_exclusive():
    # Grand total = 100. D1 (30, largest) has nothing above it -> ST. D2
    # then STARTS at exactly 30% cumulative, which is no longer inside the
    # ST band (the boundary is exclusive on the starting share) -> MT.
    sold = _sold_totals([("s", "D1", 30.0), ("s", "D2", 25.0), ("s", "D3", 25.0), ("s", "D4", 20.0)])
    result = classify_tails(sold)
    assert _badge_for(result, "s", "D1") == TailClassification.ST
    assert _badge_for(result, "s", "D2") == TailClassification.MT


def test_mt_band_ends_at_70_exclusive():
    # Grand total = 100. D1 (70) is the top item and is ST even though it
    # alone blows past both cutoffs — an item is placed by what sits ABOVE
    # it, not by where it happens to end. D2 starts at exactly 70% -> LT.
    sold = _sold_totals([("s", "D1", 70.0), ("s", "D2", 30.0)])
    result = classify_tails(sold)
    assert _badge_for(result, "s", "D1") == TailClassification.ST
    assert _badge_for(result, "s", "D2") == TailClassification.LT


def test_dominant_top_item_is_st_not_lt():
    # Regression for the "seller with zero ST" bug: when one item is the
    # overwhelming majority of a group's volume, measuring the cumulative
    # share INCLUDING the item pushed it past both cutoffs and straight to
    # LT — and since every later item started even higher, the whole group
    # came out LT with no ST at all.
    sold = _sold_totals([("s", "D_DOMINANT", 96.0), ("s", "D2", 2.0), ("s", "D3", 2.0)])
    result = classify_tails(sold)
    assert _badge_for(result, "s", "D_DOMINANT") == TailClassification.ST


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


# --------------------------------------------------------------------------- #
# classify_tails_per_seller — same rule, ranked within each seller's own
# totals instead of the marketplace-wide grand total.
# --------------------------------------------------------------------------- #
def test_ranking_is_independent_per_seller():
    # Same shape as test_ranking_is_global_across_all_sellers above, but
    # this time each seller's OWN volume is the only thing that matters:
    # seller "a" and seller "b" are perfectly symmetric within their own
    # totals (a: 1+99=100, b: 1+99=100), so their dominant DKPs must land
    # on the IDENTICAL badge — unlike classify_tails, where "a"'s D2 is ST
    # but "b"'s D4 is only MT, because there they share one marketplace
    # curve and D4 starts halfway down it.
    sold = _sold_totals(
        [
            ("a", "D1", 1.0),
            ("a", "D2", 99.0),
            ("b", "D3", 1.0),
            ("b", "D4", 99.0),
        ]
    )
    result = classify_tails_per_seller(sold)
    assert _badge_for(result, "a", "D2") == TailClassification.ST
    assert _badge_for(result, "b", "D4") == TailClassification.ST


def test_within_seller_cutoffs_still_use_30_70_bands():
    # Mirrors test_st_band_ends_at_30_exclusive — proves the same 30/70
    # rule applies, just against this seller's own denominator.
    sold = _sold_totals([("s", "D1", 30.0), ("s", "D2", 25.0), ("s", "D3", 25.0), ("s", "D4", 20.0)])
    result = classify_tails_per_seller(sold)
    assert _badge_for(result, "s", "D1") == TailClassification.ST
    assert _badge_for(result, "s", "D2") == TailClassification.MT


def test_every_seller_gets_at_least_one_st_however_concentrated():
    # The reported bug, at per-seller scale: a seller's own top item is
    # normally well over 30% of their own volume (they have a few dozen
    # DKPs, not the marketplace's thousands), which used to push it past
    # both cutoffs and leave that seller's whole list badged LT/MT with
    # zero ST. Every seller must now have a top item, in every bucket
    # they sell in.
    sold = _sold_totals(
        [("a", "D1", 96.0), ("a", "D2", 2.0), ("a", "D3", 2.0)]
        + [("b", f"D{i}", 1.0) for i in range(10, 50)]  # 40 evenly-sized DKPs
    )
    result = classify_tails_per_seller(sold)
    for seller_key in ("a", "b"):
        badges = result[result[C.SELLER_KEY] == seller_key][C.TAIL_BADGE]
        assert TailClassification.ST in set(badges), f"seller {seller_key} has no ST"


def test_ranking_is_independent_per_bucket_within_seller():
    # Bullion's volume must have no effect on how this seller's Jewelry
    # DKPs rank against each other — same guarantee as classify_tails,
    # just scoped within one seller.
    bullion = _sold_totals(
        [("s", "D_BULLION", 25.0), ("s", "DB2", 20.0), ("s", "DB3", 20.0), ("s", "DB4", 20.0), ("s", "DB5", 15.0)],
        bucket=CategoryBucket.BULLION,
    )
    jewelry = _sold_totals(
        [("s", "D1", 30.0), ("s", "D2", 40.0), ("s", "D3", 30.0)], bucket=CategoryBucket.JEWELRY
    )
    sold = pd.concat([bullion, jewelry], ignore_index=True)
    result = classify_tails_per_seller(sold)

    assert _badge_for(result, "s", "D_BULLION") == TailClassification.ST
    assert _badge_for(result, "s", "D2") == TailClassification.ST
    assert _badge_for(result, "s", "D1") == TailClassification.MT
    assert _badge_for(result, "s", "D3") == TailClassification.LT


def test_per_seller_zero_or_all_nan_net_item_fcast_pairs_are_excluded_entirely():
    sold = _sold_totals(
        [
            ("s", "D_ZERO", 0.0),
            ("s", "D_NAN", np.nan),
            ("s", "D_REAL", 10.0),
        ]
    )
    result = classify_tails_per_seller(sold)
    assert _badge_for(result, "s", "D_ZERO") is None
    assert _badge_for(result, "s", "D_NAN") is None
    assert _badge_for(result, "s", "D_REAL") is not None


def test_per_seller_returns_seller_dkp_granularity_not_dkpc():
    sold = _sold_totals([("s", "D1", 10.0), ("s", "D1", 20.0)])
    result = classify_tails_per_seller(sold)
    assert len(result) == 1
    assert set(result.columns) == {C.SELLER_KEY, C.DKP, C.TAIL_BADGE}


def test_per_seller_empty_input_returns_empty_frame():
    sold = _sold_totals([])
    result = classify_tails_per_seller(sold)
    assert result.empty
    assert set(result.columns) == {C.SELLER_KEY, C.DKP, C.TAIL_BADGE}
