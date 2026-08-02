"""
tail_classifier.py
-------------------
Classifies each (seller_key, dkp) pair from Sold_Data into an ABC/Pareto
"Item-Tail" badge — ST / MT / LT — by its share of total forecasted item
volume (sum_net_item_fcast), ranked GLOBALLY across every seller combined
(a single marketplace-wide Pareto ranking, not one per seller) — but
computed SEPARATELY per category bucket (Bullion vs Jewelry), so a DKP's
badge only ever competes against other DKPs in the same bucket.

Deliberately decoupled from atp_engine.py's matching logic: this is a
reporting/classification concern over Sold_Data alone. It does depend on
`bucket` (see atp_engine.assign_bucket), so assign_bucket() must run
BEFORE classify_tails() in the calculation pipeline.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import CanonicalColumns as C
from .config import TailClassification
from .utils import get_logger

logger = get_logger(__name__)


def _classify_within_bucket(group: pd.DataFrame) -> pd.DataFrame:
    """Rank one bucket's (seller_key, dkp) totals and assign ST/MT/LT against that bucket's own grand total."""
    ordered = group.sort_values("_total_fcast", ascending=False, kind="stable")
    bucket_total = ordered["_total_fcast"].sum()
    cum_pct = ordered["_total_fcast"].cumsum() / bucket_total * 100.0
    return ordered.assign(
        **{
            C.TAIL_BADGE: np.select(
                [
                    cum_pct <= TailClassification.CUMULATIVE_CUTOFF_ST_PCT,
                    cum_pct <= TailClassification.CUMULATIVE_CUTOFF_MT_PCT,
                ],
                [TailClassification.ST, TailClassification.MT],
                default=TailClassification.LT,
            )
        }
    )


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
        bucket). Pairs with a zero or entirely-NaN/blank total are OMITTED
        entirely — callers must left-join and treat a missing match as
        "no badge", never LT.
    """
    dkp_bucket = sold_df.groupby([C.SELLER_KEY, C.DKP])[C.BUCKET].first().reset_index()

    totals = (
        sold_df.groupby([C.SELLER_KEY, C.DKP])[C.NET_ITEM_FCAST]
        .sum(min_count=1)
        .reset_index(name="_total_fcast")
    )
    totals = totals.merge(dkp_bucket, on=[C.SELLER_KEY, C.DKP])
    totals = totals[totals["_total_fcast"].notna() & (totals["_total_fcast"] > 0)]

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
