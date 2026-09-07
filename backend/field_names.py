"""
field_names.py
---------------
User-editable overrides for the raw Excel column names the loaders expect
(see config.LiveDataColumns / config.SoldDataColumns for the built-in
defaults). A seller occasionally renames a column in their export (e.g.
Live_Data's weight column going from "Size_Name" to "Weight") — instead of
editing code, the user can fix this from the Settings panel in the UI.

Overrides are persisted to a small JSON file under the user's home
directory, so they survive app restarts and never need to be re-entered.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Final

from .config import LiveDataColumns, SoldDataColumns
from .utils import get_logger

logger = get_logger(__name__)

# Keys are stable identifiers for each editable field; values are the
# built-in raw column name expected in the uploaded file.
DEFAULT_FIELD_NAMES: Final[dict[str, str]] = {
    "live_seller_id": LiveDataColumns.SELLER_ID,
    "live_seller": LiveDataColumns.SELLER,
    "live_dkp": LiveDataColumns.DKP,
    "live_dkpc": LiveDataColumns.DKPC,
    "live_weight": LiveDataColumns.SIZE_NAME,
    "sold_seller_id": SoldDataColumns.SELLER_ID,
    "sold_seller": SoldDataColumns.SELLER,
    "sold_dkp": SoldDataColumns.DKP,
    "sold_dkpc": SoldDataColumns.DKPC,
    "sold_weight_source": SoldDataColumns.WEIGHT_SOURCE,
    "sold_category": SoldDataColumns.CATEGORY,
    "sold_net_item_fcast": SoldDataColumns.NET_ITEM_FCAST,
}

# Human-readable labels shown in the Settings UI, in display order.
FIELD_LABELS: Final[dict[str, str]] = {
    "live_seller_id": "Live_Data — Seller ID column",
    "live_seller": "Live_Data — Seller name column",
    "live_dkp": "Live_Data — DKP column",
    "live_dkpc": "Live_Data — DKPC column",
    "live_weight": "Live_Data — Weight/Size column",
    "sold_seller_id": "Sold_Data — Seller ID column",
    "sold_seller": "Sold_Data — Seller name column",
    "sold_dkp": "Sold_Data — DKP column",
    "sold_dkpc": "Sold_Data — DKPC column",
    "sold_weight_source": "Sold_Data — Weight-source (variant name) column",
    "sold_category": "Sold_Data — Category column",
    "sold_net_item_fcast": "Sold_Data — Net item forecast column",
}

_SETTINGS_DIR: Final[Path] = Path.home() / ".atp_analyzer"
_SETTINGS_FILE: Final[Path] = _SETTINGS_DIR / "field_names.json"


def _read_overrides_file() -> dict[str, str]:
    if not _SETTINGS_FILE.exists():
        return {}
    try:
        data = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read field-name overrides at %s: %s", _SETTINGS_FILE, exc)
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        key: value for key, value in data.items()
        if key in DEFAULT_FIELD_NAMES and isinstance(value, str) and value.strip()
    }


def get_field_names() -> dict[str, str]:
    """Effective raw column names: built-in defaults overridden by anything saved locally."""
    names = dict(DEFAULT_FIELD_NAMES)
    names.update(_read_overrides_file())
    return names


def save_field_names(overrides: dict[str, str]) -> dict[str, str]:
    """
    Merge `overrides` on top of whatever is already saved and persist the
    result to the local settings file. Blank/unknown keys are ignored so a
    partial update never wipes out other saved overrides.
    """
    current = _read_overrides_file()
    for key, value in overrides.items():
        if key not in DEFAULT_FIELD_NAMES:
            continue
        value = value.strip() if isinstance(value, str) else ""
        if not value or value == DEFAULT_FIELD_NAMES[key]:
            current.pop(key, None)
        else:
            current[key] = value

    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    _SETTINGS_FILE.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Saved %d field-name override(s) to %s.", len(current), _SETTINGS_FILE)
    return get_field_names()


def reset_field_names() -> dict[str, str]:
    """Delete all saved overrides, reverting every field to its built-in default."""
    if _SETTINGS_FILE.exists():
        _SETTINGS_FILE.unlink()
    return get_field_names()
