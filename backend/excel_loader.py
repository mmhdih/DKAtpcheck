"""
excel_loader.py
----------------
Reads Live_Data and Sold_Data Excel files exactly once each, validates that
the required columns are present, and normalizes both into a shared
canonical schema (see config.CanonicalColumns) so the rest of the pipeline
never has to know which source file a row came from.

Performance notes:
  - Prefers the `calamine` engine (Rust-backed, via python-calamine) for
    reading, falling back to `openpyxl` if calamine is unavailable or
    fails on a given file. calamine is materially faster on files with
    hundreds of thousands of rows.
  - All column operations below are vectorized pandas/numpy calls
    (.map/.apply over a Series, boolean masks) — there is no per-row
    Python loop over the 500k-row Live_Data file.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from typing import BinaryIO

import numpy as np
import pandas as pd

from .config import CanonicalColumns, LiveDataColumns, SoldDataColumns, get_settings
from .utils import get_logger, normalize_key, normalize_text
from .weight_parser import to_numeric_weight

logger = get_logger(__name__)


class ExcelValidationError(Exception):
    """Raised when an uploaded file is missing required columns or is unreadable."""


@dataclass
class LoadResult:
    """A canonicalized DataFrame plus any non-fatal warnings collected while loading."""

    df: pd.DataFrame
    warnings: list[str] = field(default_factory=list)


def _read_excel_any_engine(file: BinaryIO | bytes, *, source_name: str) -> pd.DataFrame:
    """
    Read an Excel file trying each configured engine in order.
    Accepts either a file-like object or raw bytes.
    """
    raw = file.read() if hasattr(file, "read") else file
    settings = get_settings()

    last_error: Exception | None = None
    for engine in settings.excel_engine_preference:
        try:
            return pd.read_excel(BytesIO(raw), engine=engine)
        except Exception as exc:  # noqa: BLE001 - we deliberately try the next engine
            last_error = exc
            logger.warning("Engine '%s' failed to read %s: %s", engine, source_name, exc)

    raise ExcelValidationError(
        f"Could not read '{source_name}' with any configured engine ({settings.excel_engine_preference}). "
        f"Last error: {last_error}"
    )


def _require_columns(df: pd.DataFrame, required: tuple[str, ...], *, source_name: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ExcelValidationError(
            f"'{source_name}' is missing required column(s): {missing}. "
            f"Found columns: {list(df.columns)}"
        )


def _drop_missing_identifiers(
    df: pd.DataFrame, *, id_columns: list[str], source_name: str, warnings: list[str]
) -> pd.DataFrame:
    """Drop rows missing any of seller/dkp/dkpc — these can never participate in matching."""
    before = len(df)
    mask = (df[id_columns] != "").all(axis=1)
    cleaned = df.loc[mask].copy()
    dropped = before - len(cleaned)
    if dropped:
        warnings.append(
            f"{source_name}: dropped {dropped} row(s) missing Seller/DKP/DKPC."
        )
    return cleaned


def load_live_data(file: BinaryIO | bytes) -> LoadResult:
    """
    Load and canonicalize the Live_Data Excel file.

    Output columns: seller, seller_key, dkp, dkpc, weight
    """
    warnings: list[str] = []
    raw_df = _read_excel_any_engine(file, source_name="Live_Data")
    _require_columns(raw_df, LiveDataColumns.REQUIRED, source_name="Live_Data")

    df = pd.DataFrame(
        {
            CanonicalColumns.SELLER: raw_df[LiveDataColumns.SELLER].map(normalize_text),
            CanonicalColumns.DKP: raw_df[LiveDataColumns.DKP].map(normalize_text),
            CanonicalColumns.DKPC: raw_df[LiveDataColumns.DKPC].map(normalize_text),
            LiveDataColumns.SIZE_NAME: raw_df[LiveDataColumns.SIZE_NAME],
        }
    )

    df = _drop_missing_identifiers(
        df,
        id_columns=[CanonicalColumns.SELLER, CanonicalColumns.DKP, CanonicalColumns.DKPC],
        source_name="Live_Data",
        warnings=warnings,
    )

    df[CanonicalColumns.SELLER_KEY] = df[CanonicalColumns.SELLER].map(normalize_key)
    df[CanonicalColumns.WEIGHT] = df[LiveDataColumns.SIZE_NAME].map(to_numeric_weight)

    unresolved = int(df[CanonicalColumns.WEIGHT].isna().sum())
    if unresolved:
        warnings.append(
            f"Live_Data: {unresolved} row(s) have an unresolvable Size_Name weight "
            f"(they still count for exact-DKPC and DKP-level matching)."
        )

    df = df.drop(columns=[LiveDataColumns.SIZE_NAME])
    logger.info("Loaded Live_Data: %d rows after cleaning.", len(df))
    return LoadResult(df=df, warnings=warnings)


def load_sold_data(file: BinaryIO | bytes) -> LoadResult:
    """
    Load and canonicalize the Sold_Data Excel file.

    Output columns: seller, seller_key, dkp, dkpc, weight
    """
    warnings: list[str] = []
    raw_df = _read_excel_any_engine(file, source_name="Sold_Data")
    _require_columns(raw_df, SoldDataColumns.REQUIRED, source_name="Sold_Data")

    df = pd.DataFrame(
        {
            CanonicalColumns.SELLER: raw_df[SoldDataColumns.SELLER].map(normalize_text),
            CanonicalColumns.DKP: raw_df[SoldDataColumns.DKP].map(normalize_text),
            CanonicalColumns.DKPC: raw_df[SoldDataColumns.DKPC].map(normalize_text),
            CanonicalColumns.SOURCE_TEXT: raw_df[SoldDataColumns.PRODUCT_ITEM_NAME],
        }
    )

    df = _drop_missing_identifiers(
        df,
        id_columns=[CanonicalColumns.SELLER, CanonicalColumns.DKP, CanonicalColumns.DKPC],
        source_name="Sold_Data",
        warnings=warnings,
    )

    df[CanonicalColumns.SELLER_KEY] = df[CanonicalColumns.SELLER].map(normalize_key)
    df[CanonicalColumns.WEIGHT] = df[CanonicalColumns.SOURCE_TEXT].map(to_numeric_weight)

    unresolved = int(df[CanonicalColumns.WEIGHT].isna().sum())
    if unresolved:
        warnings.append(
            f"Sold_Data: {unresolved} row(s) have no extractable weight in Product Item Name "
            f"(exact-DKPC matching only will apply to these)."
        )

    df = df.drop(columns=[CanonicalColumns.SOURCE_TEXT])
    logger.info("Loaded Sold_Data: %d rows after cleaning.", len(df))
    return LoadResult(df=df, warnings=warnings)
