"""
tail_classifier.py
-------------------
Classifies each (seller_key, dkp) pair from Sold_Data into an ABC/Pareto
"Item-Tail" badge — ST / MT / LT — by its share of total forecasted item
volume (sum_net_item_fcast), ranked GLOBALLY across every seller combined
(a single marketplace-wide Pareto ranking, not one per seller).

Deliberately decoupled from atp_engine.py: this is a reporting/
classification concern over Sold_Data alone, independent of ATP matching.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import CanonicalColumns as C
from .config import TailClassification
from .utils import get_logger

logger = get_logger(__name__)


def classify_tails(sold_df: pd.DataFrame) -> pd.DataFrame:
    """
    Args:
        sold_df: the FULL, non-deduplicated canonicalized Sold_Data
            DataFrame (straight out of load_sold_data()) — must not be
            pre-filtered/pre-deduped, since ranking needs the true total
            net_item_fcast per (seller_key, dkp).

    Returns:
        DataFrame [seller_key, dkp, tail_badge] — one row per
        (seller_key, dkp) pair whose SUMMED net_item_fcast (across every
        matching sold_df row) is a positive, non-NaN number. Pairs with a
        zero or entirely-NaN/blank total are OMITTED entirely — callers
        must left-join and treat a missing match as "no badge", never LT.
    """
    totals = (
        sold_df.groupby([C.SELLER_KEY, C.DKP])[C.NET_ITEM_FCAST]
        .sum(min_count=1)
        .reset_index(name="_total_fcast")
    )
    totals = totals[totals["_total_fcast"].notna() & (totals["_total_fcast"] > 0)]

    if totals.empty:
        return totals.drop(columns=["_total_fcast"]).assign(**{C.TAIL_BADGE: pd.Series(dtype=object)})

    totals = totals.sort_values("_total_fcast", ascending=False, kind="stable")
    grand_total = totals["_total_fcast"].sum()
    cum_pct = totals["_total_fcast"].cumsum() / grand_total * 100.0

    totals[C.TAIL_BADGE] = np.select(
        [
            cum_pct <= TailClassification.CUMULATIVE_CUTOFF_ST_PCT,
            cum_pct <= TailClassification.CUMULATIVE_CUTOFF_MT_PCT,
        ],
        [TailClassification.ST, TailClassification.MT],
        default=TailClassification.LT,
    )
    logger.info("Tail classification: %d (seller,dkp) pair(s) ranked.", len(totals))
    return totals[[C.SELLER_KEY, C.DKP, C.TAIL_BADGE]].reset_index(drop=True)
