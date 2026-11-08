"""
bullion_defaults.py
--------------------
User-editable list of category_name_fa values pre-selected as Bullion in
the UI (see config.CategoryBucket.DEFAULT_BULLION_CATEGORIES for the
built-in default). Lets the user change which categories count as Bullion
by default from the Settings panel, instead of editing code.

Persisted to a small JSON file next to the field-name overrides (see
field_names.py), so it survives app restarts.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Final

from .config import CategoryBucket
from .utils import get_logger, normalize_text

logger = get_logger(__name__)

_SETTINGS_DIR: Final[Path] = Path.home() / ".atp_analyzer"
_SETTINGS_FILE: Final[Path] = _SETTINGS_DIR / "bullion_categories.json"


def _clean(categories: list[str]) -> list[str]:
    """Trim, drop blanks and duplicates, keep the user's order."""
    seen: set[str] = set()
    cleaned: list[str] = []
    for category in categories:
        value = normalize_text(category) if isinstance(category, str) else ""
        if value and value not in seen:
            seen.add(value)
            cleaned.append(value)
    return cleaned


def get_default_bullion_categories() -> list[str]:
    """The saved list if there is one, otherwise the built-in default."""
    if not _SETTINGS_FILE.exists():
        return list(CategoryBucket.DEFAULT_BULLION_CATEGORIES)
    try:
        data = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read default Bullion categories at %s: %s", _SETTINGS_FILE, exc)
        return list(CategoryBucket.DEFAULT_BULLION_CATEGORIES)
    if not isinstance(data, list):
        return list(CategoryBucket.DEFAULT_BULLION_CATEGORIES)
    return _clean(data)


def save_default_bullion_categories(categories: list[str]) -> list[str]:
    """Replace the saved list. An empty list is valid (nothing pre-selected)."""
    cleaned = _clean(categories)
    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    _SETTINGS_FILE.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Saved %d default Bullion categor(ies) to %s.", len(cleaned), _SETTINGS_FILE)
    return cleaned


def reset_default_bullion_categories() -> list[str]:
    """Delete the saved list, reverting to the built-in default."""
    if _SETTINGS_FILE.exists():
        _SETTINGS_FILE.unlink()
    return list(CategoryBucket.DEFAULT_BULLION_CATEGORIES)
