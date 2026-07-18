import math

import pytest

from backend.weight_parser import extract_weight_from_text, to_numeric_weight


@pytest.mark.parametrize(
    "text, expected",
    [
        ("... | 0.65 گرم |", 0.65),
        ("... | 1 گرم |", 1.0),
        ("... | 3.25 گرم |", 3.25),
        ("چیزی بدون وزن", None),
        ("", None),
        ("۰٫۶۵ گرم", 0.65),          # Persian digits + Arabic decimal separator
        ("2گرم", 2.0),                  # no space between number and unit
        ("پیش از عدد گرم است", None),  # unit present but no leading number
    ],
)
def test_extract_weight_from_text(text, expected):
    assert extract_weight_from_text(text) == expected


def test_extract_weight_from_text_none_and_nan():
    assert extract_weight_from_text(None) is None
    assert extract_weight_from_text(float("nan")) is None


@pytest.mark.parametrize(
    "value, expected",
    [
        (2.5, 2.5),
        (0, 0.0),
        ("2.5", 2.5),
        ("... | 0.65 گرم |", 0.65),
        (None, None),
        (float("nan"), None),
        ("no weight here", None),
    ],
)
def test_to_numeric_weight(value, expected):
    result = to_numeric_weight(value)
    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected)
