"""
app.py
-------
FastAPI application exposing the ATP Analyzer as a REST API.

Endpoints:
    GET  /api/v1/health                      liveness check
    GET  /api/v1/config                      UI-facing defaults (tolerance presets, limits)
    POST /api/v1/calculate                   run the full ATP pipeline on two uploaded files
    GET  /api/v1/download/summary/{result_id}    Summary.xlsx
    GET  /api/v1/download/missing/{result_id}    ATP_Missing.xlsx

This module intentionally contains no business logic — it validates
HTTP-level concerns (file size, presence of both files) and delegates
everything else to excel_loader / atp_engine / summary_generator /
missing_generator.
"""
from __future__ import annotations

import io

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .atp_engine import ATPEngine, ATPIndex
from .config import get_settings
from .excel_loader import ExcelValidationError, load_live_data, load_sold_data
from .missing_generator import build_missing, missing_to_excel_bytes
from .models import CalculationMeta, CalculationResponse, ErrorResponse, MissingRow, SummaryRow
from .summary_generator import build_summary, summary_to_excel_bytes
from .utils import ResultCache, get_logger, timer

settings = get_settings()
logger = get_logger(__name__)

app = FastAPI(title=settings.app_name, version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_cache = ResultCache(
    ttl_seconds=settings.result_cache_ttl_seconds,
    max_entries=settings.result_cache_max_entries,
)

_MISSING_PREVIEW_ROWS = 200


async def _read_upload_within_limit(upload: UploadFile, *, label: str) -> bytes:
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    data = await upload.read()
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"{label} exceeds the {settings.max_upload_size_mb}MB upload limit.",
        )
    if not data:
        raise HTTPException(status_code=400, detail=f"{label} is empty.")
    return data


@app.get(f"{settings.api_v1_prefix}/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get(f"{settings.api_v1_prefix}/config")
def public_config() -> dict:
    """Defaults the frontend should use instead of hardcoding them itself."""
    return {
        "tolerance_presets": settings.tolerance_presets,
        "default_tolerance_pct": settings.default_tolerance_pct,
        "max_upload_size_mb": settings.max_upload_size_mb,
    }


@app.post(
    f"{settings.api_v1_prefix}/calculate",
    response_model=CalculationResponse,
    responses={400: {"model": ErrorResponse}, 413: {"model": ErrorResponse}},
)
async def calculate(
    live_file: UploadFile = File(..., description="Live_Data.xlsx"),
    sold_file: UploadFile = File(..., description="Sold_Data.xlsx"),
    tolerance_pct: float = Form(..., ge=0, description="Weight tolerance percentage"),
) -> CalculationResponse:
    if tolerance_pct > 100:
        raise HTTPException(status_code=400, detail="tolerance_pct above 100 is almost certainly a mistake.")

    live_bytes = await _read_upload_within_limit(live_file, label="Live_Data file")
    sold_bytes = await _read_upload_within_limit(sold_file, label="Sold_Data file")

    with timer() as t:
        try:
            live_result = load_live_data(io.BytesIO(live_bytes))
            sold_result = load_sold_data(io.BytesIO(sold_bytes))
        except ExcelValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        index = ATPIndex.build(live_result.df)
        engine = ATPEngine(index=index, tolerance_pct=tolerance_pct)
        atp_result = engine.compute(sold_result.df)

        summary_df = build_summary(atp_result)
        missing_df = build_missing(atp_result)

    result_id = _cache.put(summary_df=summary_df, missing_df=missing_df)

    warnings = live_result.warnings + sold_result.warnings
    meta = CalculationMeta(
        live_rows_loaded=len(live_result.df),
        sold_rows_loaded=len(sold_result.df),
        unique_sellers=len(index.dkpc_by_seller),
        sold_dkpc_unique=len(atp_result.dkpc_results),
        sold_dkp_unique=len(atp_result.dkp_results),
        sold_weight_unresolved_count=int(atp_result.dkpc_results["weight"].isna().sum()),
        tolerance_pct=tolerance_pct,
        execution_seconds=round(t["seconds"], 3),
        warnings=warnings,
    )

    logger.info(
        "Calculation %s complete in %.3fs (live=%d, sold=%d, sellers=%d).",
        result_id, t["seconds"], meta.live_rows_loaded, meta.sold_rows_loaded, meta.unique_sellers,
    )

    return CalculationResponse(
        result_id=result_id,
        summary=[
            SummaryRow(seller=seller, dkpc_atp_pct=dkpc_pct, dkp_atp_pct=dkp_pct)
            for seller, dkpc_pct, dkp_pct in zip(
                summary_df["Seller"], summary_df["DKPC ATP %"], summary_df["DKP ATP %"]
            )
        ],
        missing_preview=[
            MissingRow(seller=seller, dkp=dkp, dkpc=dkpc)
            for seller, dkp, dkpc in zip(
                missing_df["Seller"].head(_MISSING_PREVIEW_ROWS),
                missing_df["DKP"].head(_MISSING_PREVIEW_ROWS),
                missing_df["DKPC"].head(_MISSING_PREVIEW_ROWS),
            )
        ],
        missing_total_count=len(missing_df),
        meta=meta,
    )


def _get_cache_entry_or_404(result_id: str):
    entry = _cache.get(result_id)
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail="Result not found. It may have expired — please run the calculation again.",
        )
    return entry


@app.get(f"{settings.api_v1_prefix}/download/summary/{{result_id}}")
def download_summary(result_id: str) -> StreamingResponse:
    entry = _get_cache_entry_or_404(result_id)
    xlsx_bytes = summary_to_excel_bytes(entry.summary_df)
    return StreamingResponse(
        io.BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Summary.xlsx"},
    )


@app.get(f"{settings.api_v1_prefix}/download/missing/{{result_id}}")
def download_missing(result_id: str) -> StreamingResponse:
    entry = _get_cache_entry_or_404(result_id)
    xlsx_bytes = missing_to_excel_bytes(entry.missing_df)
    return StreamingResponse(
        io.BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=ATP_Missing.xlsx"},
    )
