"""
weight_parser.py
-----------------
Extracts a numeric weight (in grams) from free-form text such as:

    "کوکو دارک چاکلت | 0.65 گرم |"
    "شکلات تلخ 70% | 1 گرم |"
    "پرالین بادام | 3.25 گرم |"

If no recognizable weight pattern exists, the weight is considered
unavailable (returns None) — per the spec, such sold rows fall back to
exact-DKPC matching only.

Also used for Live_Data's Size_Name column via `to_numeric_weight`, which
accepts either an already-numeric value or the same free-form text pattern.
"""
from __future__ import annotations

import math
import re
from typing import Any

from .config import WeightParsing

# Translate Persian/Arabic-Indic digits to ASCII so a single regex handles
# "0.65 گرم" and "۰٫۶۵ گرم" identically.
_DIGIT_TRANSLATION = str.maketrans(
    {**{p: a for p, a in zip(WeightParsing.PERSIAN_DIGITS, WeightParsing.ASCII_DIGITS)}}
)

# Arabic decimal separator (٫, U+066B) and Arabic thousands separator (٬,
# U+066C) normalized to ASCII equivalents before parsing.
_DECIMAL_SEPARATOR_TRANSLATION = str.maketrans({"٫": ".", "٬": ""})

# Zero-width non-joiner and non-breaking space frequently appear around
# Persian text; treat them as ordinary whitespace for matching purposes.
_INVISIBLE_WHITESPACE_TRANSLATION = str.maketrans({"\u200c": " ", "\u00a0": " "})


def _build_weight_pattern() -> re.Pattern[str]:
    units = "|".join(re.escape(u) for u in WeightParsing.UNIT_TOKENS)
    # Number: digits, optional decimal part. Unit may be separated from the
    # number by zero or more spaces (Excel exports are inconsistent here).
    return re.compile(rf"(\d+(?:\.\d+)?)\s*(?:{units})\b")


_WEIGHT_PATTERN = _build_weight_pattern()


def _pre_clean(text: str) -> str:
    text = text.translate(_INVISIBLE_WHITESPACE_TRANSLATION)
    text = text.translate(_DIGIT_TRANSLATION)
    text = text.translate(_DECIMAL_SEPARATOR_TRANSLATION)
    return text


def extract_weight_from_text(text: Any) -> float | None:
    """
    Search free-form text for a "<number> <unit>" weight pattern.

    Returns:
        The parsed weight as a float, or None if no pattern was found
        (or the input was empty/NaN).
    """
    if text is None:
        return None
    if isinstance(text, float) and math.isnan(text):
        return None

    cleaned = _pre_clean(str(text))
    match = _WEIGHT_PATTERN.search(cleaned)
    if not match:
        return None

    try:
        return float(match.group(1))
    except ValueError:
        return None


def to_numeric_weight(value: Any) -> float | None:
    """
    Convert a Live_Data Size_Name cell to a numeric weight.

    Handles three cases, in order:
      1. Already numeric (int/float, not NaN) -> used as-is.
      2. A plain numeric string (possibly with Persian digits/decimal
         separators) -> parsed directly.
      3. Free-form text containing a "<number> گرم" pattern -> delegated
         to extract_weight_from_text.

    Returns None if none of the above apply (weight unavailable).
    """
    if value is None:
        return None

    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)

    text = _pre_clean(str(value)).strip()
    if not text:
        return None

    try:
        return float(text)
    except ValueError:
        pass

    return extract_weight_from_text(text)
