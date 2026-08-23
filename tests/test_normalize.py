from __future__ import annotations

from datetime import date, datetime

import pytest

from statement_reconciler.normalize import (
    DAY_FIRST,
    MONTH_FIRST,
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


class TestGroupingSeparators:
    """Repeated separators are grouping, never decimals -- a number has one decimal point.

    Missing this made European-formatted amounts a false break: "1.234.567" read as a decimal
    would never equal 1234567 from the other side.
    """

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("1.234.567", "1234567"),
            ("1,234,567", "1234567"),
            ("1.234.567,89", "1234567.89"),
            ("1,234,567.89", "1234567.89"),
        ],
    )
    def test_repeated_separators_are_thousands(self, value, expected):
        assert norm_number(value) == expected

    def test_european_grouping_matches_the_plain_number(self):
        assert norm_number("1.234.567") == norm_number(1234567)

    def test_both_conventions_agree_with_each_other(self):
        assert norm_number("1.234.567,89") == norm_number("1,234,567.89")

    def test_a_lone_separator_stays_ambiguous_but_consistent(self):
        """ "1.234" could be either; what matters is that it reads the same way every time."""
        assert norm_number("1.234") == norm_number("1.234")
        assert norm_number("1,234") == "1234"


class TestDateOrderResolvesAmbiguity:
    def test_the_same_string_reads_both_ways(self):
        assert norm_date("03/04/2026", DAY_FIRST) == "2026-04-03"
        assert norm_date("03/04/2026", MONTH_FIRST) == "2026-03-04"

    def test_a_us_statement_agrees_with_an_iso_export_under_month_first(self):
        """The false break this setting exists to prevent."""
        assert norm_date("03/04/2026", MONTH_FIRST) == norm_date("2026-03-04", MONTH_FIRST)

    def test_unambiguous_forms_ignore_the_setting(self):
        for value in ("2026-03-04", "04-Mar-2026", "March 4, 2026"):
            assert norm_date(value, DAY_FIRST) == norm_date(value, MONTH_FIRST)

    def test_an_impossible_reading_falls_through_to_the_other(self):
        """31 cannot be a month, so 12/31/2026 is unambiguous whatever the setting says."""
        assert norm_date("12/31/2026", DAY_FIRST) == "2026-12-31"

    def test_default_is_day_first(self):
        assert norm_date("03/04/2026") == norm_date("03/04/2026", DAY_FIRST)
