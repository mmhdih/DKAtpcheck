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

    @field_validator("tolerance_pct")
    @classmethod
    def _sane_upper_bound(cls, value: float) -> float:
        if value > 100:
            raise ValueError("tolerance_pct above 100 is almost certainly a mistake")
        return value


class SummaryRow(BaseModel):
    """One row of the Summary table — percentages only, per the spec."""

    seller: str
    dkpc_atp_pct: float = Field(..., ge=0, le=100)
    dkp_atp_pct: float = Field(..., ge=0, le=100)


class MissingRow(BaseModel):
    """One row of the ATP_Missing table — a sold DKPC that is not ATP."""

    seller: str
    dkp: str
    dkpc: str


class CalculationMeta(BaseModel):
    """Diagnostics about a calculation run, shown in the UI and useful for support."""

    live_rows_loaded: int
    sold_rows_loaded: int
    unique_sellers: int
    sold_dkpc_unique: int
    sold_dkp_unique: int
    sold_weight_unresolved_count: int
    tolerance_pct: float
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
    meta: CalculationMeta


class ErrorResponse(BaseModel):
    """Uniform error body for 4xx/5xx responses."""

    detail: str
