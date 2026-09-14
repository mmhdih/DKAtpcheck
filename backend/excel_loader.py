"""
excel_loader.py
----------------
Reads Live_Data and Sold_Data files (.xlsx or .csv) exactly once each,
validates that the required columns are present, and normalizes both into
a shared canonical schema (see config.CanonicalColumns) so the rest of
the pipeline never has to know which source file a row came from.

Seller_ID (Live_Data) / marketplace_seller_id (Sold_Data) is the join key
between the two files (seller_key = normalized seller_id, casefolded) —
seller display name is retained separately, for output only.

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

import re
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any, BinaryIO, Iterable

import pandas as pd

from .config import CanonicalColumns, LiveDataColumns, get_settings
from .field_names import get_field_names
from .utils import get_logger, normalize_id, normalize_text
from .weight_parser import to_numeric_weight

logger = get_logger(__name__)


class ExcelValidationError(Exception):
    """Raised when an uploaded file is missing required columns or is unreadable."""


@dataclass
class LoadResult:
    """A canonicalized DataFrame plus any non-fatal warnings collected while loading."""

    df: pd.DataFrame
    warnings: list[str] = field(default_factory=list)


def _is_csv_filename(filename: str | None) -> bool:
    if not filename:
        return False
    settings = get_settings()
    lowered = filename.lower()
    return any(lowered.endswith(ext) for ext in settings.csv_extensions)


def _read_csv_any_encoding(raw: bytes, *, source_name: str) -> pd.DataFrame:
    """
    Read a .csv file trying each configured encoding in order, with the
    delimiter auto-detected (Persian/Iranian Excel exports use ',' or ';'
    inconsistently depending on regional settings).
    """
    settings = get_settings()

    last_error: Exception | None = None
    for encoding in settings.csv_encoding_preference:
        try:
            return pd.read_csv(BytesIO(raw), sep=None, engine="python", encoding=encoding)
        except Exception as exc:  # noqa: BLE001 - we deliberately try the next encoding
            last_error = exc
            logger.warning("Encoding '%s' failed to read %s as CSV: %s", encoding, source_name, exc)

    raise ExcelValidationError(
        f"Could not read '{source_name}' as CSV with any configured encoding "
        f"({settings.csv_encoding_preference}). Last error: {last_error}"
    )


def _read_tabular_any_engine(
    file: BinaryIO | bytes, *, source_name: str, filename: str | None = None
) -> pd.DataFrame:
    """
    Read an uploaded Live_Data/Sold_Data file, dispatching to CSV or Excel
    parsing based on the filename's extension. Accepts either a file-like
    object or raw bytes.
    """
    raw = file.read() if hasattr(file, "read") else file

    if _is_csv_filename(filename):
        return _read_csv_any_encoding(raw, source_name=source_name)

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


_HEADER_SEPARATOR_RE = re.compile(r"[\s_\-]+")


def _header_key(value: Any) -> str:
    """
    Fold a column header down to a comparison key: normalize_text (NFKC,
    Persian/Arabic look-alikes unified, whitespace collapsed and trimmed),
    then '_'/'-'/space runs collapsed to a single space, case folded.

    So "DKP_Name", "DKP NAME", "dkp name" and a stray-trailing-space
    "DKP Name " all key to "dkp name". Exports rename columns cosmetically
    all the time; a header that differs only in case, separator or padding
    is the same column, and silently treating it as absent is how a whole
    column comes out blank.
    """
    return _HEADER_SEPARATOR_RE.sub(" ", normalize_text(value)).strip().casefold()


class _HeaderResolver:
    """
    Maps the column names the app is configured to look for onto the
    headers a given file actually has.

    An exact hit always wins; otherwise a single header with the same
    folded key (see _header_key) is accepted. Two headers folding to the
    same key is genuine ambiguity, so neither is picked — the caller then
    reports the column as missing rather than guessing.
    """

    def __init__(self, df: pd.DataFrame) -> None:
        self.columns: list[str] = [str(c) for c in df.columns]
        self._by_key: dict[str, list[str]] = {}
        for column in df.columns:
            self._by_key.setdefault(_header_key(column), []).append(column)

    def resolve(self, configured: str) -> str | None:
        if configured in self._by_key.get(_header_key(configured), []):
            return configured
        matches = self._by_key.get(_header_key(configured), [])
        return matches[0] if len(matches) == 1 else None

    def resolve_any(self, candidates: Iterable[str]) -> str | None:
        """First of `candidates` that resolves, or None if none do."""
        for candidate in candidates:
            resolved = self.resolve(candidate)
            if resolved is not None:
                return resolved
        return None


def _resolve_required(
    resolver: _HeaderResolver, configured: dict[str, str], *, source_name: str
) -> dict[str, str]:
    """
    Resolve every required field to a real header, or raise listing both
    what was expected and what the file actually has.
    """
    resolved = {key: resolver.resolve(name) for key, name in configured.items()}
    missing = [configured[key] for key, actual in resolved.items() if actual is None]
    if missing:
        raise ExcelValidationError(
            f"'{source_name}' is missing required column(s): {missing}. "
            f"Found columns: {resolver.columns}"
        )
    for key, actual in resolved.items():
        if actual != configured[key]:
            logger.info(
                "%s: matched configured column '%s' to header '%s'.",
                source_name, configured[key], actual,
            )
    return resolved  # type: ignore[return-value]


def _drop_missing_identifiers(
    df: pd.DataFrame, *, id_columns: list[str], source_name: str, warnings: list[str]
) -> pd.DataFrame:
    """Drop rows missing any of seller_id/dkp/dkpc — these can never participate in matching."""
    before = len(df)
    mask = (df[id_columns] != "").all(axis=1)
    cleaned = df.loc[mask].copy()
    dropped = before - len(cleaned)
    if dropped:
        warnings.append(
            f"{source_name}: dropped {dropped} row(s) missing Seller_ID/DKP/DKPC."
        )
    return cleaned


def load_live_data(file: BinaryIO | bytes, *, filename: str | None = None) -> LoadResult:
    """
    Load and canonicalize the Live_Data file (.xlsx or .csv).

    Output columns: seller_id, seller, seller_key, dkp, dkp_name, dkpc, weight
    """
    warnings: list[str] = []
    names = get_field_names()
    raw_df = _read_tabular_any_engine(file, source_name="Live_Data", filename=filename)
    resolver = _HeaderResolver(raw_df)
    columns = _resolve_required(
        resolver,
        {key: names[key] for key in
         ("live_seller_id", "live_seller", "live_dkp", "live_dkpc", "live_weight")},
        source_name="Live_Data",
    )

    # The raw weight text is parked under the canonical source_text name
    # (same as the Sold_Data loader) rather than under its own header: a
    # file whose weight column is literally called "weight" would otherwise
    # collide with the canonical weight column and get dropped with it.
    weight_source_col = columns["live_weight"]
    df = pd.DataFrame(
        {
            CanonicalColumns.SELLER_ID: raw_df[columns["live_seller_id"]].map(normalize_id),
            CanonicalColumns.SELLER: raw_df[columns["live_seller"]].map(normalize_text),
            CanonicalColumns.DKP: raw_df[columns["live_dkp"]].map(normalize_id),
            CanonicalColumns.DKPC: raw_df[columns["live_dkpc"]].map(normalize_id),
            CanonicalColumns.SOURCE_TEXT: raw_df[weight_source_col],
        }
    )

    # Product name is report-only enrichment, never a matching input, so a
    # file without that column loads fine — names just come out blank. The
    # configured name is tried first, then the spellings assortment
    # exports are known to use, since a wrong guess here can only affect
    # what a report displays.
    dkp_name_col = resolver.resolve(names["live_dkp_name"]) or resolver.resolve_any(
        LiveDataColumns.DKP_NAME_ALIASES
    )
    if dkp_name_col is None:
        df[CanonicalColumns.DKP_NAME] = ""
        warnings.append(
            f"Live_Data: no product-name column found (looked for '{names['live_dkp_name']}'), "
            f"so DKP Name will be blank in every output. The file's columns are: "
            f"{resolver.columns}. Put the right one in Settings → column names."
        )
    else:
        df[CanonicalColumns.DKP_NAME] = raw_df[dkp_name_col].map(normalize_text)
        if not (df[CanonicalColumns.DKP_NAME] != "").any():
            warnings.append(
                f"Live_Data: the product-name column '{dkp_name_col}' is present but empty in "
                f"every row, so DKP Name will be blank in every output."
            )

    df = _drop_missing_identifiers(
        df,
        id_columns=[CanonicalColumns.SELLER_ID, CanonicalColumns.DKP, CanonicalColumns.DKPC],
        source_name="Live_Data",
        warnings=warnings,
    )

    df[CanonicalColumns.SELLER_KEY] = df[CanonicalColumns.SELLER_ID].str.casefold()
    df[CanonicalColumns.WEIGHT] = df[CanonicalColumns.SOURCE_TEXT].map(to_numeric_weight)

    unresolved = int(df[CanonicalColumns.WEIGHT].isna().sum())
    if unresolved:
        warnings.append(
            f"Live_Data: {unresolved} row(s) have an unresolvable '{weight_source_col}' weight "
            f"(they still count for exact-DKPC and DKP-level matching)."
        )

    df = df.drop(columns=[CanonicalColumns.SOURCE_TEXT])
    logger.info("Loaded Live_Data: %d rows after cleaning.", len(df))
    return LoadResult(df=df, warnings=warnings)


def load_sold_data(file: BinaryIO | bytes, *, filename: str | None = None) -> LoadResult:
    """
    Load and canonicalize the Sold_Data file (.xlsx or .csv).

    Output columns: seller_id, seller, seller_key, dkp, dkpc, weight,
                    category, net_item_fcast
    """
    warnings: list[str] = []
    names = get_field_names()
    raw_df = _read_tabular_any_engine(file, source_name="Sold_Data", filename=filename)
    resolver = _HeaderResolver(raw_df)
    columns = _resolve_required(
        resolver,
        {key: names[key] for key in (
            "sold_seller_id", "sold_seller", "sold_dkp", "sold_dkpc",
            "sold_weight_source", "sold_category", "sold_net_item_fcast",
        )},
        source_name="Sold_Data",
    )

    df = pd.DataFrame(
        {
            CanonicalColumns.SELLER_ID: raw_df[columns["sold_seller_id"]].map(normalize_id),
            CanonicalColumns.SELLER: raw_df[columns["sold_seller"]].map(normalize_text),
            CanonicalColumns.DKP: raw_df[columns["sold_dkp"]].map(normalize_id),
            CanonicalColumns.DKPC: raw_df[columns["sold_dkpc"]].map(normalize_id),
            CanonicalColumns.SOURCE_TEXT: raw_df[columns["sold_weight_source"]],
            CanonicalColumns.CATEGORY: raw_df[columns["sold_category"]].map(normalize_text),
            CanonicalColumns.NET_ITEM_FCAST: pd.to_numeric(
                raw_df[columns["sold_net_item_fcast"]], errors="coerce"
            ),
        }
    )

    df = _drop_missing_identifiers(
        df,
        id_columns=[CanonicalColumns.SELLER_ID, CanonicalColumns.DKP, CanonicalColumns.DKPC],
        source_name="Sold_Data",
        warnings=warnings,
    )

    df[CanonicalColumns.SELLER_KEY] = df[CanonicalColumns.SELLER_ID].str.casefold()
    df[CanonicalColumns.WEIGHT] = df[CanonicalColumns.SOURCE_TEXT].map(to_numeric_weight)

    unresolved = int(df[CanonicalColumns.WEIGHT].isna().sum())
    if unresolved:
        warnings.append(
            f"Sold_Data: {unresolved} row(s) have no extractable weight in '{columns['sold_weight_source']}' "
            f"(exact-DKPC matching only will apply to these)."
        )

    df = df.drop(columns=[CanonicalColumns.SOURCE_TEXT])
    logger.info("Loaded Sold_Data: %d rows after cleaning.", len(df))
    return LoadResult(df=df, warnings=warnings)
