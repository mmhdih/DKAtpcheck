"""
tail_classifier.py
-------------------
Classifies each (seller_key, dkp) pair from Sold_Data into an ABC/Pareto
"Item-Tail" badge — ST / MT / LT — by its share of total forecasted item
volume (sum_net_item_fcast), computed SEPARATELY per category bucket
(Bullion vs Jewelry), so a DKP's badge only ever competes against other
DKPs in the same bucket. Two variants of this ranking are offered:

  - classify_tails: ranked GLOBALLY across every seller combined (a
    single marketplace-wide Pareto ranking per bucket, not one per
    seller) — feeds the "Category ST/MT/LT PER Seller" tab.
  - classify_tails_per_seller: ranked separately for EACH seller's own
    (bucket, dkp) totals — a seller's own top 30% of their own sold
    volume is ST, regardless of how that compares to other sellers —
    feeds the standalone "Per-Seller Item-Tail" tab.

Deliberately decoupled from atp_engine.py's matching logic: this is a
reporting/classification concern over Sold_Data alone. It does depend on
`bucket` (see atp_engine.assign_bucket), so assign_bucket() must run
BEFORE either classify function in the calculation pipeline.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import CanonicalColumns as C
from .config import TailClassification
from .utils import get_logger

logger = get_logger(__name__)


def _classify_within_bucket(group: pd.DataFrame) -> pd.DataFrame:
    """
    Rank one group's (seller_key, dkp) totals and assign ST/MT/LT against
    that group's own grand total.

    An item is placed by the volume share accumulated *before* it, so an
    item that straddles a cutoff belongs to the band it STARTS in, not the
    one it overshoots into. This is what makes the top item always ST
    (nothing is accumulated before it).

    Measuring the share *including* the item instead would mean the top
    item can only be ST when that single item is under 30% of the group's
    volume on its own. Marketplace-wide that is nearly always true, so it
    never showed; but ranked within one seller — only a few dozen DKPs,
    usually with one clear best-seller — the top item routinely exceeds
    30% and would fall straight to MT or LT, leaving that seller with no
    ST at all.
    """
    ordered = group.sort_values("_total_fcast", ascending=False, kind="stable")
    bucket_total = ordered["_total_fcast"].sum()
    cum_pct_before = (
        (ordered["_total_fcast"].cumsum() - ordered["_total_fcast"]) / bucket_total * 100.0
    )
    return ordered.assign(
        **{
            C.TAIL_BADGE: np.select(
                [
                    cum_pct_before < TailClassification.CUMULATIVE_CUTOFF_ST_PCT,
                    cum_pct_before < TailClassification.CUMULATIVE_CUTOFF_MT_PCT,
                ],
                [TailClassification.ST, TailClassification.MT],
                default=TailClassification.LT,
            )
        }
    )


def _dkp_totals(sold_df: pd.DataFrame) -> pd.DataFrame:
    """
    (seller_key, dkp) -> summed net_item_fcast + bucket, filtered down to
    pairs whose total is a positive, non-NaN number (the shared precursor
    to both classify_tails and classify_tails_per_seller).
    """
    dkp_bucket = sold_df.groupby([C.SELLER_KEY, C.DKP])[C.BUCKET].first().reset_index()

    totals = (
        sold_df.groupby([C.SELLER_KEY, C.DKP])[C.NET_ITEM_FCAST]
        .sum(min_count=1)
        .reset_index(name="_total_fcast")
    )
    totals = totals.merge(dkp_bucket, on=[C.SELLER_KEY, C.DKP])
    return totals[totals["_total_fcast"].notna() & (totals["_total_fcast"] > 0)]


def classify_tails(sold_df: pd.DataFrame) -> pd.DataFrame:
    """
    Args:
        sold_df: the FULL, non-deduplicated canonicalized Sold_Data
            DataFrame, with a `bucket` column already assigned (call
            atp_engine.assign_bucket() first) — must not be
            pre-filtered/pre-deduped on rows, since ranking needs the true
            total net_item_fcast per (seller_key, dkp).

    Returns:
        DataFrame [seller_key, dkp, tail_badge] — one row per
        (seller_key, dkp) pair whose SUMMED net_item_fcast (across every
        matching sold_df row) is a positive, non-NaN number. Ranking and
        the 30%/70% cumulative cutoffs are computed independently within
        each bucket (a DKP's badge never depends on volume in the other
        bucket, nor on which seller it belongs to). Pairs with a zero or
        entirely-NaN/blank total are OMITTED entirely — callers must
        left-join and treat a missing match as "no badge", never LT.
    """
    totals = _dkp_totals(sold_df)

    if totals.empty:
        return totals.drop(columns=["_total_fcast", C.BUCKET]).assign(
            **{C.TAIL_BADGE: pd.Series(dtype=object)}
        )

    badged = pd.concat(
        [_classify_within_bucket(group) for _, group in totals.groupby(C.BUCKET, sort=False)],
        ignore_index=True,
    )
    logger.info(
        "Tail classification: %d (seller,dkp) pair(s) ranked across %d bucket(s).",
        len(badged), badged[C.BUCKET].nunique(),
    )
    return badged[[C.SELLER_KEY, C.DKP, C.TAIL_BADGE]]


def classify_tails_per_seller(sold_df: pd.DataFrame) -> pd.DataFrame:
    """
    Same ABC/Pareto Item-Tail rule as classify_tails, but the ranking and
    30%/70% cumulative cutoffs are computed independently for EACH SELLER's
    own (bucket, dkp) totals, instead of across the whole marketplace: a
    seller's own top 30% of their own forecasted sales volume is ST no
    matter how that volume compares to any other seller's.

    Args:
        sold_df: same precondition as classify_tails (full, non-deduped,
            `bucket` already assigned).

    Returns:
        DataFrame [seller_key, dkp, tail_badge] — one row per
        (seller_key, dkp) pair whose SUMMED net_item_fcast is a positive,
        non-NaN number. Pairs with a zero/entirely-NaN/blank total are
        OMITTED entirely, same exclusion rule as classify_tails.
    """
    totals = _dkp_totals(sold_df)

    if totals.empty:
        return totals.drop(columns=["_total_fcast", C.BUCKET]).assign(
            **{C.TAIL_BADGE: pd.Series(dtype=object)}
        )

    badged = pd.concat(
        [_classify_within_bucket(group) for _, group in totals.groupby([C.SELLER_KEY, C.BUCKET], sort=False)],
        ignore_index=True,
    )
    logger.info(
        "Per-seller tail classification: %d (seller,dkp) pair(s) ranked across %d (seller,bucket) group(s).",
        len(badged), badged.groupby([C.SELLER_KEY, C.BUCKET]).ngroups if len(badged) else 0,
    )
    return badged[[C.SELLER_KEY, C.DKP, C.TAIL_BADGE]]
