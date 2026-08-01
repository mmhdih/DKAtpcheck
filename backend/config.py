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

    SELLER_ID: Final[str] = "Seller_ID"
    SELLER: Final[str] = "Seller_Name"
    DKP: Final[str] = "DKP"
    DKPC: Final[str] = "DKPC"
    SIZE_NAME: Final[str] = "Size_Name"

    REQUIRED: Final[tuple[str, ...]] = (SELLER_ID, SELLER, DKP, DKPC, SIZE_NAME)


class SoldDataColumns:
    """Raw column headers expected in the Sold_Data Excel file."""

    SELLER_ID: Final[str] = "marketplace_seller_id"
    SELLER: Final[str] = "marketplace_seller_name"
    DKP: Final[str] = "product_id"
    DKPC: Final[str] = "product_variant_id"
    WEIGHT_SOURCE: Final[str] = "product_variant_name_fa"
    CATEGORY: Final[str] = "category_name_fa"
    NET_ITEM_FCAST: Final[str] = "sum_net_item_fcast"

    REQUIRED: Final[tuple[str, ...]] = (
        SELLER_ID, SELLER, DKP, DKPC, WEIGHT_SOURCE, CATEGORY, NET_ITEM_FCAST,
    )


# --------------------------------------------------------------------------- #
# Canonical internal column names.
# Every loader normalizes its DataFrame to these names so the rest of the
# pipeline (atp_engine, summary_generator, missing_generator) never has to
# know which source file a row came from.
# --------------------------------------------------------------------------- #
class CanonicalColumns:
    SELLER_ID: Final[str] = "seller_id"      # normalized identifier; the actual join key source
    SELLER: Final[str] = "seller"            # display name (trimmed, original casing)
    SELLER_KEY: Final[str] = "seller_key"    # casefolded seller_id; join key used throughout the engine
    DKP: Final[str] = "dkp"
    DKPC: Final[str] = "dkpc"
    WEIGHT: Final[str] = "weight"          # float, NaN if unresolvable
    SOURCE_TEXT: Final[str] = "source_text"  # raw text weight was parsed from (debugging)
    CATEGORY: Final[str] = "category"        # Sold_Data only; "" if blank
    NET_ITEM_FCAST: Final[str] = "net_item_fcast"  # Sold_Data only; float, NaN if blank
    BUCKET: Final[str] = "bucket"            # "Bullion" | "Jewelry"; assigned at request time
    TAIL_BADGE: Final[str] = "tail_badge"    # "ST" | "MT" | "LT" | NaN; assigned at request time


# --------------------------------------------------------------------------- #
# Category bucket labels (Bullion vs Jewelry split)
# --------------------------------------------------------------------------- #
class CategoryBucket:
    BULLION: Final[str] = "Bullion"
    JEWELRY: Final[str] = "Jewelry"


# --------------------------------------------------------------------------- #
# Item-Tail (ABC/Pareto) classification, ranked globally by sum_net_item_fcast
# --------------------------------------------------------------------------- #
class TailClassification:
    ST: Final[str] = "ST"
    MT: Final[str] = "MT"
    LT: Final[str] = "LT"
    ALL: Final[tuple[str, ...]] = (ST, MT, LT)

    # Cumulative-percentage cutoffs (inclusive), standard ABC/Pareto split.
    CUMULATIVE_CUTOFF_ST_PCT: Final[float] = 30.0
    CUMULATIVE_CUTOFF_MT_PCT: Final[float] = 70.0


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
    max_upload_size_mb: int = 500

    # Excel engines to try, in order. "calamine" (python-calamine, Rust-backed)
    # is dramatically faster than openpyxl on files with hundreds of
    # thousands of rows; openpyxl is the guaranteed-available fallback.
    excel_engine_preference: list[str] = ["calamine", "openpyxl"]

    # Accepted upload file extensions (case-insensitive), in addition to
    # Excel (.xlsx) — a plain .csv is read via pandas.read_csv instead of
    # pd.read_excel; everything else about the pipeline is unchanged.
    csv_extensions: list[str] = [".csv"]

    # Text encodings to try, in order, when reading an uploaded .csv.
    # utf-8-sig handles both plain UTF-8 and UTF-8-with-BOM (the common
    # "CSV UTF-8" export option in Excel); cp1256 is the common legacy
    # Windows codepage for Arabic/Persian text when a file was exported
    # without explicitly choosing UTF-8.
    csv_encoding_preference: list[str] = ["utf-8-sig", "cp1256", "utf-8"]

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
