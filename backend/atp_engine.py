"""
atp_engine.py
--------------
The core ATP computation. Two independent things are computed here:

  1. DKPC-level ATP (weight-aware): exact DKPC match first, then — only if
     no exact match and a sold weight is resolvable — a same-seller weight
     search within +/- tolerance%.
  2. DKP-level ATP (weight-INDEPENDENT): true iff the seller has at least
     one live DKPC under that DKP, regardless of weight.

Both are computed on UNIQUE (seller, dkp) / (seller, dkpc) pairs — sale
quantity is irrelevant per the spec.

Design for extensibility: DKPC-level matching is a small rule pipeline
(Chain of Responsibility). Adding a new rule later means adding one class
to `DEFAULT_DKPC_RULES` (or passing a custom list into ATPEngine) — nothing
else in this file, or in summary_generator/missing_generator, needs to
change.

Performance design: see ATPIndex docstring below.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import CanonicalColumns as C
from .models import ATPMatchType
from .utils import get_logger

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Seller-partitioned index over Live_Data — built once, queried many times.
# --------------------------------------------------------------------------- #
@dataclass
class ATPIndex:
    """
    Pre-computed, per-seller lookup structures built from Live_Data in a
    single pass (via groupby — no per-row Python loop over 500k rows).

    Attributes:
        dkpc_by_seller: seller_key -> set of live DKPCs (exact match, O(1) lookup)
        dkp_by_seller:  seller_key -> set of live DKPs (weight-independent, O(1) lookup)
        weights_by_seller: seller_key -> sorted np.ndarray of live weights
            (NaN-free). Used with np.searchsorted for O(log n) "is any
            weight within [lo, hi]" range queries instead of an O(n) scan
            per sold row.
    """

    dkpc_by_seller: dict[str, frozenset[str]]
    dkp_by_seller: dict[str, frozenset[str]]
    weights_by_seller: dict[str, np.ndarray]

    @classmethod
    def build(cls, live_df: pd.DataFrame) -> "ATPIndex":
        dkpc_by_seller = {
            seller_key: frozenset(group[C.DKPC])
            for seller_key, group in live_df.groupby(C.SELLER_KEY)[[C.DKPC]]
        }
        dkp_by_seller = {
            seller_key: frozenset(group[C.DKP])
            for seller_key, group in live_df.groupby(C.SELLER_KEY)[[C.DKP]]
        }

        weighted = live_df.dropna(subset=[C.WEIGHT])
        weights_by_seller = {
            seller_key: np.sort(group[C.WEIGHT].to_numpy(dtype=float))
            for seller_key, group in weighted.groupby(C.SELLER_KEY)[[C.WEIGHT]]
        }

        logger.info(
            "Built ATPIndex for %d sellers (%d with at least one resolvable live weight).",
            len(dkpc_by_seller),
            len(weights_by_seller),
        )
        return cls(
            dkpc_by_seller=dkpc_by_seller,
            dkp_by_seller=dkp_by_seller,
            weights_by_seller=weights_by_seller,
        )

    def has_weight_within_tolerance(self, seller_key: str, weight: float, tolerance_pct: float) -> bool:
        """O(log n) check: does this seller have any live weight in [weight*(1-t), weight*(1+t)]?"""
        arr = self.weights_by_seller.get(seller_key)
        if arr is None or arr.size == 0:
            return False
        low = weight * (1 - tolerance_pct / 100.0)
        high = weight * (1 + tolerance_pct / 100.0)
        left = np.searchsorted(arr, low, side="left")
        right = np.searchsorted(arr, high, side="right")
        return right > left


# --------------------------------------------------------------------------- #
# DKPC-level rule pipeline (Chain of Responsibility)
# --------------------------------------------------------------------------- #
class ATPRule(ABC):
    """
    A single matching rule. `evaluate` returns True if this rule grants
    ATP status for the given sold (seller_key, dkpc, weight) against the
    index. ATPEngine runs rules in order and stops at the first True.
    """

    match_type: ATPMatchType

    @abstractmethod
    def evaluate(self, *, seller_key: str, dkpc: str, weight: float | None, index: ATPIndex) -> bool: ...


class ExactDKPCRule(ATPRule):
    """Step 1: the exact DKPC exists in Live_Data for the same seller."""

    match_type = ATPMatchType.EXACT_DKPC

    def evaluate(self, *, seller_key: str, dkpc: str, weight: float | None, index: ATPIndex) -> bool:
        return dkpc in index.dkpc_by_seller.get(seller_key, frozenset())


class WeightToleranceRule(ATPRule):
    """
    Step 2: only applies if the sold weight is resolvable. Any live DKPC of
    the same seller with weight within +/- tolerance% grants ATP.
    Sold rows with no resolvable weight never reach this rule with a match
    (weight=None short-circuits to False, meaning exact-match-only applies).
    """

    match_type = ATPMatchType.WEIGHT_TOLERANCE

    def __init__(self, tolerance_pct: float) -> None:
        self.tolerance_pct = tolerance_pct

    def evaluate(self, *, seller_key: str, dkpc: str, weight: float | None, index: ATPIndex) -> bool:
        if weight is None or (isinstance(weight, float) and np.isnan(weight)):
            return False
        return index.has_weight_within_tolerance(seller_key, weight, self.tolerance_pct)


def default_dkpc_rules(tolerance_pct: float) -> list[ATPRule]:
    """The standard two-step pipeline described in the spec, in order."""
    return [ExactDKPCRule(), WeightToleranceRule(tolerance_pct)]


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #
@dataclass
class ATPResult:
    """Everything downstream modules (summary/missing generators) need."""

    dkpc_results: pd.DataFrame  # columns: seller, seller_key, dkp, dkpc, weight, match_type, is_atp
    dkp_results: pd.DataFrame  # columns: seller, seller_key, dkp, is_atp


class ATPEngine:
    """
    Orchestrates the ATP computation for a Sold_Data DataFrame against a
    pre-built ATPIndex.

    To add a future rule: pass a custom `dkpc_rules` list (or subclass and
    override `_default_rules`). The rest of the compute() pipeline —
    deduplication to unique DKPCs, DKP-level independence from weight, and
    the output shape — does not need to change.
    """

    def __init__(self, index: ATPIndex, tolerance_pct: float, dkpc_rules: list[ATPRule] | None = None) -> None:
        self.index = index
        self.tolerance_pct = tolerance_pct
        self.dkpc_rules = dkpc_rules or default_dkpc_rules(tolerance_pct)

    def _classify_dkpc(self, seller_key: str, dkpc: str, weight: float | None) -> ATPMatchType:
        for rule in self.dkpc_rules:
            if rule.evaluate(seller_key=seller_key, dkpc=dkpc, weight=weight, index=self.index):
                return rule.match_type
        return ATPMatchType.NOT_ATP

    def compute(self, sold_df: pd.DataFrame) -> ATPResult:
        # --- DKPC-level: unique per (seller_key, dkpc); quantity is irrelevant ---
        unique_dkpc = sold_df.drop_duplicates(subset=[C.SELLER_KEY, C.DKPC]).reset_index(drop=True)

        match_types = [
            self._classify_dkpc(seller_key, dkpc, weight)
            for seller_key, dkpc, weight in zip(
                unique_dkpc[C.SELLER_KEY], unique_dkpc[C.DKPC], unique_dkpc[C.WEIGHT]
            )
        ]
        unique_dkpc = unique_dkpc.assign(
            match_type=match_types,
            is_atp=[m != ATPMatchType.NOT_ATP for m in match_types],
        )

        # --- DKP-level: unique per (seller_key, dkp); weight-independent ---
        unique_dkp = sold_df.drop_duplicates(subset=[C.SELLER_KEY, C.DKP]).reset_index(drop=True)
        unique_dkp = unique_dkp.assign(
            is_atp=[
                dkp in self.index.dkp_by_seller.get(seller_key, frozenset())
                for seller_key, dkp in zip(unique_dkp[C.SELLER_KEY], unique_dkp[C.DKP])
            ]
        )[[C.SELLER, C.SELLER_KEY, C.DKP, "is_atp"]]

        logger.info(
            "ATP computed: %d unique sold DKPCs (%d ATP), %d unique sold DKPs (%d ATP).",
            len(unique_dkpc),
            int(unique_dkpc["is_atp"].sum()),
            len(unique_dkp),
            int(unique_dkp["is_atp"].sum()),
        )

        return ATPResult(
            dkpc_results=unique_dkpc[[C.SELLER, C.SELLER_KEY, C.DKP, C.DKPC, C.WEIGHT, "match_type", "is_atp"]],
            dkp_results=unique_dkp,
        )
