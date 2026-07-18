"""
config.py
---------
Single source of truth for anything that could change without touching
business logic: raw Excel column names, internal canonical column names,
default values exposed to the UI, and runtime/service settings.

Rationale:
    If a seller ever renames an Excel column (e.g. "Seller Name" ->
    "Seller"), only this file needs to change. No other module should
    ever hardcode a raw column name.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Final

from pydantic_settings import BaseSettings, SettingsConfigDict


# --------------------------------------------------------------------------- #
# Raw Excel column names (as they appear in the uploaded files)
# --------------------------------------------------------------------------- #
class LiveDataColumns:
    """Raw column headers expected in the Live_Data Excel file."""

    SELLER: Final[str] = "Seller_Name"
    DKP: Final[str] = "DKP"
    DKPC: Final[str] = "DKPC"
    SIZE_NAME: Final[str] = "Size_Name"

    REQUIRED: Final[tuple[str, ...]] = (SELLER, DKP, DKPC, SIZE_NAME)


class SoldDataColumns:
    """Raw column headers expected in the Sold_Data Excel file."""

    SELLER: Final[str] = "Seller Name"
    DKP: Final[str] = "Product Id"
    DKPC: Final[str] = "Product Item Id"
    PRODUCT_ITEM_NAME: Final[str] = "Product Item Name"

    REQUIRED: Final[tuple[str, ...]] = (SELLER, DKP, DKPC, PRODUCT_ITEM_NAME)


# --------------------------------------------------------------------------- #
# Canonical internal column names.
# Every loader normalizes its DataFrame to these names so the rest of the
# pipeline (atp_engine, summary_generator, missing_generator) never has to
# know which source file a row came from.
# --------------------------------------------------------------------------- #
class CanonicalColumns:
    SELLER: Final[str] = "seller"            # display name (trimmed, original casing)
    SELLER_KEY: Final[str] = "seller_key"    # normalized (trimmed + casefolded) join key
    DKP: Final[str] = "dkp"
    DKPC: Final[str] = "dkpc"
    WEIGHT: Final[str] = "weight"          # float, NaN if unresolvable
    SOURCE_TEXT: Final[str] = "source_text"  # raw text weight was parsed from (debugging)


# --------------------------------------------------------------------------- #
# Weight parsing constants
# --------------------------------------------------------------------------- #
class WeightParsing:
    # Persian word for "gram". Kept as a list so additional unit spellings
    # (e.g. an English "gr" fallback) can be added without touching the regex
    # builder in weight_parser.py.
    UNIT_TOKENS: Final[tuple[str, ...]] = ("گرم",)

    # Accept both '.' and Persian/Arabic decimal separators, and both
    # ASCII and Persian digits, since Excel exports from Iranian sellers
    # frequently mix these.
    PERSIAN_DIGITS: Final[str] = "۰۱۲۳۴۵۶۷۸۹"
    ASCII_DIGITS: Final[str] = "0123456789"


# --------------------------------------------------------------------------- #
# Runtime / service settings (overridable via environment variables)
# --------------------------------------------------------------------------- #
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ATP_", env_file=".env", extra="ignore")

    app_name: str = "ATP Analyzer"
    api_v1_prefix: str = "/api/v1"

    # CORS - Streamlit runs on a different port/origin during local dev.
    cors_allow_origins: list[str] = ["*"]

    # Tolerance presets shown as quick-select buttons in the UI.
    # The user may still submit any non-negative float; this is not a
    # hardcoded restriction, only a UX convenience (per requirements).
    tolerance_presets: list[float] = [0, 5, 10, 15, 20]
    default_tolerance_pct: float = 10.0

    # Upload limits.
    max_upload_size_mb: int = 100

    # Excel engines to try, in order. "calamine" (python-calamine, Rust-backed)
    # is dramatically faster than openpyxl on files with hundreds of
    # thousands of rows; openpyxl is the guaranteed-available fallback.
    excel_engine_preference: list[str] = ["calamine", "openpyxl"]

    # In-memory result cache (see utils.ResultCache). A single-process
    # deployment is assumed; swap this for a Redis-backed cache here if
    # the service is ever scaled to multiple workers/instances.
    result_cache_ttl_seconds: int = 60 * 30  # 30 minutes
    result_cache_max_entries: int = 50

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Cached Settings accessor so the whole app shares one instance."""
    return Settings()
