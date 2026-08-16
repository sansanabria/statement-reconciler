from __future__ import annotations

from datetime import date, datetime

import pytest

from statement_reconciler.normalize import (
    mask_shape,
    norm_date,
    norm_number,
    norm_quantity,
    norm_text,
    normalize_field,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-03-02", "2026-03-02"),
        ("02/03/2026", "2026-03-02"),
        ("02.03.2026", "2026-03-02"),
        ("02-Mar-2026", "2026-03-02"),
        ("2 March 2026", "2026-03-02"),
        ("20260302", "2026-03-02"),
        ("2026-03-02 00:00:00", "2026-03-02"),
        (date(2026, 3, 2), "2026-03-02"),
        (datetime(2026, 3, 2, 14, 30), "2026-03-02"),
        ("", ""),
        (None, ""),
        ("not a date", "NOT A DATE"),
    ],
)
def test_norm_date(value, expected):
    assert norm_date(value) == expected


def test_both_sides_of_the_same_day_agree():
    assert norm_date("02-Mar-2026") == norm_date(datetime(2026, 3, 2))


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1,234.50", "1234.5"),
        ("1.234,50", "1234.5"),
        ("1 234.50", "1234.5"),
        ("1'234.50", "1234.5"),
        (1234.5, "1234.5"),
        ("10.50", "10.5"),
        ("10", "10"),
        ("(99.00)", "-99"),
        ("99.00-", "-99"),
        ("-99.00", "-99"),
        ("EUR 1,234.50", "1234.5"),
        ("1,234.50 EUR", "1234.5"),
        ("0", "0"),
        ("0.00", "0"),
        ("", ""),
        (None, ""),
        ("n/a", "N/A"),
    ],
)
def test_norm_number(value, expected):
    assert norm_number(value) == expected


def test_decimal_comma_versus_thousands_comma():
    assert norm_number("1,234") == "1234"  # thousands group
    assert norm_number("1,23") == "1.23"  # decimal comma


def test_float_and_printed_string_agree():
    assert norm_number(1234.5) == norm_number("1,234.50")


@pytest.mark.parametrize(("value", "expected"), [("12", "12"), (12.0, "12"), ("12.0", "12")])
def test_norm_quantity(value, expected):
    assert norm_quantity(value) == expected


def test_norm_text_collapses_and_upcases():
    assert norm_text("  alpha   widget\n") == "ALPHA WIDGET"
    assert norm_text(None) == ""


def test_normalize_field_dispatches_and_falls_back():
    assert normalize_field("amount", "1,000.00") == "1000"
    assert normalize_field("unknown_field", " x ") == "X"


def test_mask_shape_hides_values_but_keeps_structure():
    assert mask_shape("ABC-123 xy") == "AAA-999 aa"
