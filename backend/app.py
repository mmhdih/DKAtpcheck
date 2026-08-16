"""
app.py
-------
FastAPI application exposing the ATP Analyzer as a REST API.

Endpoints:
    GET  /api/v1/health                        liveness check
    GET  /api/v1/config                        UI-facing defaults (tolerance presets, limits)
    POST /api/v1/sold-data/categories           distinct category_name_fa values in a Sold_Data file
    POST /api/v1/calculate                      run the full ATP pipeline on two uploaded files
    GET  /api/v1/download/summary/{result_id}       Summary.xlsx
    GET  /api/v1/download/missing/{result_id}       ATP_Missing.xlsx
    GET  /api/v1/download/tail-summary/{result_id}  Tail_Summary.xlsx
    GET  /api/v1/download/tail-dkp-list/{result_id} Tail_DKP_List.xlsx
    GET  /api/v1/download/seller-zip/{result_id}    ATP_Missing_by_Seller.zip (opt-in)
    GET  /api/v1/download/tail-seller-zip/{result_id} Tail_DKP_List_by_Seller.zip (opt-in)
    GET  /api/v1/templates/live-data            Live_Data_Template.xlsx
    GET  /api/v1/templates/sold-data            Sold_Data_Template.xlsx

This module intentionally contains no business logic — it validates
HTTP-level concerns (file size, presence of both files) and delegates
everything else to excel_loader / atp_engine / tail_classifier /
summary_generator / missing_generator / tail_summary_generator /
seller_export / templates.
"""
from __future__ import annotations

import io

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .atp_engine import ATPEngine, ATPIndex, assign_bucket
from .config import CanonicalColumns, TailClassification, get_settings
from .excel_loader import ExcelValidationError, load_live_data, load_sold_data
from .missing_generator import build_missing, missing_to_excel_bytes
from .models import (
    CalculationMeta,
    CalculationResponse,
    CategoryListResponse,
    ErrorResponse,
    MissingRow,
    SummaryRow,
    TailSummaryRow,
)
from .seller_export import build_seller_missing_zip
from .summary_generator import build_summary, summary_to_excel_bytes
from .tail_classifier import classify_tails
from .tail_summary_generator import (
    build_tail_dkp_list,
    build_tail_dkp_zip,
    build_tail_summary,
    tail_dkp_list_to_excel_bytes,
    tail_summary_to_excel_bytes,
)
from .templates import build_live_data_template_bytes, build_sold_data_template_bytes
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
        "tail_badges": list(TailClassification.ALL),
    }


@app.post(
    f"{settings.api_v1_prefix}/sold-data/categories",
    response_model=CategoryListResponse,
    responses={400: {"model": ErrorResponse}, 413: {"model": ErrorResponse}},
)
async def sold_data_categories(
    sold_file: UploadFile = File(..., description="Sold_Data.xlsx or .csv"),
) -> CategoryListResponse:
    sold_bytes = await _read_upload_within_limit(sold_file, label="Sold_Data file")
    try:
        sold_result = load_sold_data(io.BytesIO(sold_bytes), filename=sold_file.filename)
    except ExcelValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    categories = sorted({c for c in sold_result.df[CanonicalColumns.CATEGORY] if c})
    return CategoryListResponse(categories=categories)


@app.post(
    f"{settings.api_v1_prefix}/calculate",
    response_model=CalculationResponse,
    responses={400: {"model": ErrorResponse}, 413: {"model": ErrorResponse}},
)
async def calculate(
    live_file: UploadFile = File(..., description="Live_Data.xlsx or .csv"),
    sold_file: UploadFile = File(..., description="Sold_Data.xlsx or .csv"),
    tolerance_pct: float = Form(..., ge=0, description="Weight tolerance percentage"),
    bullion_categories: list[str] = Form(
        default_factory=list, description="category_name_fa values to treat as Bullion"
    ),
    tail_badges: list[str] = Form(
        default_factory=lambda: list(TailClassification.ALL),
        description="Which ST/MT/LT Item-Tail badges to include",
    ),
    generate_seller_zip: bool = Form(False, description="Also build the per-seller NOT-ATP ZIP export"),
    generate_tail_seller_zip: bool = Form(
        False, description="Also build the per-seller ST/MT/LT Item-Tail ZIP export"
    ),
) -> CalculationResponse:
    if tolerance_pct > 100:
        raise HTTPException(status_code=400, detail="tolerance_pct above 100 is almost certainly a mistake.")

    # An empty/omitted selection is indistinguishable over multipart form
    # encoding (an empty list produces zero repeated fields, same as never
    # sending the field at all) — both are treated as "no filter" (all
    # three badges), which is also the safer default if a UI multiselect
    # is accidentally cleared.
    selected_badges = set(tail_badges) if tail_badges else set(TailClassification.ALL)
    unknown_badges = selected_badges - set(TailClassification.ALL)
    if unknown_badges:
        raise HTTPException(status_code=400, detail=f"Unknown tail_badges: {sorted(unknown_badges)}")

    live_bytes = await _read_upload_within_limit(live_file, label="Live_Data file")
    sold_bytes = await _read_upload_within_limit(sold_file, label="Sold_Data file")

    with timer() as t:
        try:
            live_result = load_live_data(io.BytesIO(live_bytes), filename=live_file.filename)
            sold_result = load_sold_data(io.BytesIO(sold_bytes), filename=sold_file.filename)
        except ExcelValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        sold_df = sold_result.df

        # Bucket must be assigned before tail classification: ST/MT/LT is
        # ranked separately within each bucket, so a DKP's badge never
        # depends on volume in the other bucket.
        sold_df = assign_bucket(sold_df, bullion_categories=set(bullion_categories))

        tail_by_dkp = classify_tails(sold_df)
        sold_df = sold_df.merge(
            tail_by_dkp, on=[CanonicalColumns.SELLER_KEY, CanonicalColumns.DKP], how="left"
        )

        if selected_badges != set(TailClassification.ALL):
            sold_df = sold_df[sold_df[CanonicalColumns.TAIL_BADGE].isin(selected_badges)].reset_index(
                drop=True
            )

        index = ATPIndex.build(live_result.df)
        engine = ATPEngine(index=index, tolerance_pct=tolerance_pct)
        atp_result = engine.compute(sold_df)

        summary_df = build_summary(atp_result)
        missing_df = build_missing(atp_result)
        tail_summary_df = build_tail_summary(atp_result)
        tail_dkp_list_df = build_tail_dkp_list(atp_result)

        seller_zip_bytes = build_seller_missing_zip(atp_result) if generate_seller_zip else None
        tail_seller_zip_bytes = build_tail_dkp_zip(atp_result) if generate_tail_seller_zip else None

    result_id = _cache.put(
        summary_df=summary_df,
        missing_df=missing_df,
        tail_summary_df=tail_summary_df,
        tail_dkp_list_df=tail_dkp_list_df,
        seller_zip_bytes=seller_zip_bytes,
        tail_seller_zip_bytes=tail_seller_zip_bytes,
    )

    warnings = live_result.warnings + sold_result.warnings
    meta = CalculationMeta(
        live_rows_loaded=len(live_result.df),
        sold_rows_loaded=len(sold_result.df),
        unique_sellers=len(index.dkpc_by_seller),
        sold_dkpc_unique=len(atp_result.dkpc_results),
        sold_dkp_unique=len(atp_result.dkp_results),
        sold_weight_unresolved_count=int(atp_result.dkpc_results["weight"].isna().sum()),
        tolerance_pct=tolerance_pct,
        bullion_categories_selected=bullion_categories,
        tail_badges_selected=sorted(selected_badges),
        seller_zip_generated=seller_zip_bytes is not None,
        tail_seller_zip_generated=tail_seller_zip_bytes is not None,
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
            SummaryRow(
                seller_id=seller_id,
                seller=seller,
                dkpc_atp_pct_bullion=dkpc_b,
                dkp_atp_pct_bullion=dkp_b,
                dkpc_atp_pct_jewelry=dkpc_j,
                dkp_atp_pct_jewelry=dkp_j,
            )
            for seller_id, seller, dkpc_b, dkp_b, dkpc_j, dkp_j in zip(
                summary_df["Seller ID"], summary_df["Seller"],
                summary_df["DKPC ATP % (Bullion)"], summary_df["DKP ATP % (Bullion)"],
                summary_df["DKPC ATP % (Jewelry)"], summary_df["DKP ATP % (Jewelry)"],
            )
        ],
        missing_preview=[
            MissingRow(seller_id=sid, seller=s, dkp=dkp, dkpc=dkpc, category=cat, bucket=bkt)
            for sid, s, dkp, dkpc, cat, bkt in zip(
                missing_df["Seller ID"].head(_MISSING_PREVIEW_ROWS),
                missing_df["Seller"].head(_MISSING_PREVIEW_ROWS),
                missing_df["DKP"].head(_MISSING_PREVIEW_ROWS),
                missing_df["DKPC"].head(_MISSING_PREVIEW_ROWS),
                missing_df["Category"].head(_MISSING_PREVIEW_ROWS),
                missing_df["Bucket"].head(_MISSING_PREVIEW_ROWS),
            )
        ],
        missing_total_count=len(missing_df),
        tail_summary=[
            TailSummaryRow(
                seller_id=sid, seller=s,
                st_available=st_a, st_unavailable=st_u,
                mt_available=mt_a, mt_unavailable=mt_u,
                lt_available=lt_a, lt_unavailable=lt_u,
            )
            for sid, s, st_a, st_u, mt_a, mt_u, lt_a, lt_u in zip(
                tail_summary_df["Seller ID"], tail_summary_df["Seller"],
                tail_summary_df["ST Available"], tail_summary_df["ST Unavailable"],
                tail_summary_df["MT Available"], tail_summary_df["MT Unavailable"],
                tail_summary_df["LT Available"], tail_summary_df["LT Unavailable"],
            )
        ],
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


@app.get(f"{settings.api_v1_prefix}/download/tail-summary/{{result_id}}")
def download_tail_summary(result_id: str) -> StreamingResponse:
    entry = _get_cache_entry_or_404(result_id)
    xlsx_bytes = tail_summary_to_excel_bytes(entry.tail_summary_df)
    return StreamingResponse(
        io.BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Tail_Summary.xlsx"},
    )


@app.get(f"{settings.api_v1_prefix}/download/tail-dkp-list/{{result_id}}")
def download_tail_dkp_list(result_id: str) -> StreamingResponse:
    entry = _get_cache_entry_or_404(result_id)
    xlsx_bytes = tail_dkp_list_to_excel_bytes(entry.tail_dkp_list_df)
    return StreamingResponse(
        io.BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Tail_DKP_List.xlsx"},
    )


@app.get(f"{settings.api_v1_prefix}/download/seller-zip/{{result_id}}")
def download_seller_zip(result_id: str) -> StreamingResponse:
    entry = _get_cache_entry_or_404(result_id)
    if entry.seller_zip_bytes is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Seller ZIP export was not generated for this result. "
                "Re-run the calculation with 'generate_seller_zip' enabled."
            ),
        )
    return StreamingResponse(
        io.BytesIO(entry.seller_zip_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=ATP_Missing_by_Seller.zip"},
    )


@app.get(f"{settings.api_v1_prefix}/download/tail-seller-zip/{{result_id}}")
def download_tail_seller_zip(result_id: str) -> StreamingResponse:
    entry = _get_cache_entry_or_404(result_id)
    if entry.tail_seller_zip_bytes is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Tail-by-seller ZIP export was not generated for this result. "
                "Re-run the calculation with 'generate_tail_seller_zip' enabled."
            ),
        )
    return StreamingResponse(
        io.BytesIO(entry.tail_seller_zip_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=Tail_DKP_List_by_Seller.zip"},
    )


@app.get(f"{settings.api_v1_prefix}/templates/live-data")
def download_live_data_template() -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(build_live_data_template_bytes()),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Live_Data_Template.xlsx"},
    )


@app.get(f"{settings.api_v1_prefix}/templates/sold-data")
def download_sold_data_template() -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(build_sold_data_template_bytes()),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Sold_Data_Template.xlsx"},
    )
