"""
models.py
---------
Pydantic schemas that define the API contract between the FastAPI backend
and any client (the Streamlit frontend, or anything else).

These are intentionally kept separate from the internal data structures
used inside atp_engine.py (e.g. per-seller index dictionaries), which are
implementation detail and should be free to change without breaking the
API contract.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator

from .config import TailClassification


class WeightResolution(str, Enum):
    """How a sold row's weight was determined, for transparency in reports."""

    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"


class ATPMatchType(str, Enum):
    """
    Which rule granted ATP status to a sold DKPC, if any.
    Kept as an explicit enum (rather than a bare bool) so future rules
    can be added and still be distinguishable in diagnostics/exports.
    """

    EXACT_DKPC = "exact_dkpc"
    WEIGHT_TOLERANCE = "weight_tolerance"
    NOT_ATP = "not_atp"


class CalculationRequest(BaseModel):
    """Form-field payload accompanying the two uploaded Excel files."""

    tolerance_pct: float = Field(
        ...,
        ge=0,
        description="Weight tolerance percentage. 0 means exact weight match only.",
    )
    bullion_categories: list[str] = Field(
        default_factory=list,
        description="category_name_fa values to treat as Bullion; everything else is Jewelry.",
    )
    tail_badges: list[str] = Field(
        default_factory=lambda: list(TailClassification.ALL),
        description="Which ST/MT/LT Item-Tail badges to include. Defaults to all three (no filtering).",
    )
    generate_seller_zip: bool = Field(
        False, description="Also build the per-seller NOT-ATP ZIP export."
    )
    generate_seller_tail_zip: bool = Field(
        False,
        description=(
            "Also build the per-seller ZIP export of the standalone Per-Seller "
            "Item-Tail tab (each seller's own ST/MT/LT ranking, split one xlsx per seller)."
        ),
    )

    @field_validator("tolerance_pct")
    @classmethod
    def _sane_upper_bound(cls, value: float) -> float:
        if value > 100:
            raise ValueError("tolerance_pct above 100 is almost certainly a mistake")
        return value


class CategoryListResponse(BaseModel):
    """Response of POST /api/v1/sold-data/categories."""

    categories: list[str]


class SummaryRow(BaseModel):
    """One row of the Summary table — percentages only, per the spec, split by category bucket."""

    seller_id: str
    seller: str
    dkpc_atp_pct_bullion: float = Field(..., ge=0, le=100)
    dkp_atp_pct_bullion: float = Field(..., ge=0, le=100)
    dkpc_atp_pct_jewelry: float = Field(..., ge=0, le=100)
    dkp_atp_pct_jewelry: float = Field(..., ge=0, le=100)


class MissingRow(BaseModel):
    """One row of the ATP_Missing table — a sold DKPC that is not ATP."""

    seller_id: str
    seller: str
    dkp: str
    dkpc: str
    category: str
    bucket: str


class TailSummaryRow(BaseModel):
    """
    One row of a Tail Summary table — DKP counts per seller, per ST/MT/LT
    badge, by ATP status. Shared shape for both the marketplace-wide
    "Category ST/MT/LT PER Seller" tab and the standalone, per-seller-
    ranked "Per-Seller Item-Tail" tab — only how the badge was computed
    differs between the two.
    """

    seller_id: str
    seller: str
    st_available: int = Field(..., ge=0)
    st_unavailable: int = Field(..., ge=0)
    mt_available: int = Field(..., ge=0)
    mt_unavailable: int = Field(..., ge=0)
    lt_available: int = Field(..., ge=0)
    lt_unavailable: int = Field(..., ge=0)


class CalculationMeta(BaseModel):
    """Diagnostics about a calculation run, shown in the UI and useful for support."""

    live_rows_loaded: int
    sold_rows_loaded: int
    unique_sellers: int
    sold_dkpc_unique: int
    sold_dkp_unique: int
    sold_weight_unresolved_count: int
    tolerance_pct: float
    bullion_categories_selected: list[str] = Field(default_factory=list)
    tail_badges_selected: list[str] = Field(default_factory=lambda: list(TailClassification.ALL))
    seller_zip_generated: bool = False
    seller_tail_zip_generated: bool = False
    execution_seconds: float
    warnings: list[str] = Field(default_factory=list)


class CalculationResponse(BaseModel):
    """Full response of POST /api/v1/calculate."""

    result_id: str
    summary: list[SummaryRow]
    missing_preview: list[MissingRow] = Field(
        default_factory=list,
        description=(
            "First N rows of ATP_Missing for on-screen preview. The full "
            "table is retrieved via the dedicated download endpoint."
        ),
    )
    missing_total_count: int
    tail_summary: list[TailSummaryRow] = Field(default_factory=list)
    seller_tail_summary: list[TailSummaryRow] = Field(default_factory=list)
    meta: CalculationMeta


class ErrorResponse(BaseModel):
    """Uniform error body for 4xx/5xx responses."""

    detail: str
