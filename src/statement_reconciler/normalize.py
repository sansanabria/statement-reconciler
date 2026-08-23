"""Turn the two sides' spellings of the same value into one canonical string.

A PDF prints "1,234.50" where the spreadsheet holds the float 1234.5; one writes "02-Mar-2026",
the other "2026-03-02". None of that is a real difference, and treating it as one buries the
genuine mismatches. Every normaliser here is total: it never raises, and it returns the input
stripped rather than guessing when it cannot parse. An unparseable value that appears the same
way on both sides still matches.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

#: How to read a purely numeric date whose meaning depends on locale: is 03/04/2026 the 3rd of
#: April or the 4th of March? Nothing in the document says, so the source declares it.
DAY_FIRST = "day_first"
MONTH_FIRST = "month_first"
DATE_ORDERS = (DAY_FIRST, MONTH_FIRST)

# Unambiguous forms, tried before anything locale-dependent. An ISO date or a spelled-out month
# means the same thing everywhere.
_UNAMBIGUOUS_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y.%m.%d",
    "%Y%m%d",
    "%d-%b-%Y",
    "%d %b %Y",
    "%d-%B-%Y",
    "%d %B %Y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%d-%b-%y",
    "%b %d, %y",
)

# The ambiguous ones. Whichever list comes first wins, which is the whole point of date_order:
# 03/04/2026 parses as 3 April under day_first and 4 March under month_first.
_DAY_FIRST_FORMATS = ("%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%y", "%d/%m/%y")
_MONTH_FIRST_FORMATS = ("%m-%d-%Y", "%m/%d/%Y", "%m.%d.%Y", "%m-%d-%y", "%m/%d/%y")

_FORMATS_BY_ORDER = {
    DAY_FIRST: _UNAMBIGUOUS_FORMATS + _DAY_FIRST_FORMATS + _MONTH_FIRST_FORMATS,
    MONTH_FIRST: _UNAMBIGUOUS_FORMATS + _MONTH_FIRST_FORMATS + _DAY_FIRST_FORMATS,
}

_WHITESPACE = re.compile(r"\s+")
_NUMERIC_CHARS = re.compile(r"^[\d\s.,'’\-+()]+$")
_TRAILING_SIGN = re.compile(r"^(?P<body>.*?)(?P<sign>[-+])$")


def norm_text(value: Any) -> str:
    """Collapse whitespace and upper-case. Used for descriptions and any free-text key field."""
    if value is None:
        return ""
    return _WHITESPACE.sub(" ", str(value)).strip().upper()


def norm_date(value: Any, order: str = DAY_FIRST) -> str:
    """Return an ISO date string, or the cleaned input when it is not a recognisable date.

    `order` decides only the genuinely ambiguous numeric forms. Both sides of one source are
    read with the same order, so a source that writes 03/04/2026 on the statement and
    2026-04-03 in the export still agrees -- provided the order matches how the sender writes
    dates. Set it per source with `date_order` in the config.
    """
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()

    text = _WHITESPACE.sub(" ", str(value)).strip()
    if not text:
        return ""
    # A spreadsheet cell read as a datetime often arrives as "2026-03-02 00:00:00".
    head = text.split(" ")[0] if " 00:00:00" in text else text
    for fmt in _FORMATS_BY_ORDER.get(order, _FORMATS_BY_ORDER[DAY_FIRST]):
        try:
            return datetime.strptime(head, fmt).date().isoformat()
        except ValueError:
            continue
    return text.upper()


def norm_number(value: Any, decimals: int = 6) -> str:
    """Return a canonical decimal string, or the cleaned input when it is not a number.

    Handles thousands separators (comma, space, apostrophe), decimal commas, parentheses and
    trailing signs for negatives, and a currency symbol or code stuck to either end. Trailing
    zeros are dropped so "10.50" and "10.5" and 10.5 all agree.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).upper()
    if isinstance(value, (int, float)):
        return _format_number(float(value), decimals)

    text = str(value).strip()
    if not text:
        return ""

    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative, text = True, text[1:-1].strip()
    sign_match = _TRAILING_SIGN.match(text)
    if sign_match and sign_match.group("body").strip():
        negative = negative or sign_match.group("sign") == "-"
        text = sign_match.group("body").strip()

    # Strip a currency symbol or an alphabetic code from either end, but nothing in the middle:
    # a value with embedded letters is not a number and should fall through unchanged.
    cleaned = re.sub(r"^[^\d\-+(.]+|(?<=[\d)])[^\d.,)]+$", "", text).strip()
    if not cleaned or not _NUMERIC_CHARS.match(cleaned):
        return norm_text(value)

    cleaned = cleaned.replace(" ", "").replace("'", "").replace("’", "")
    cleaned = _unify_decimal_separator(cleaned)
    try:
        number = float(cleaned)
    except ValueError:
        return norm_text(value)
    if negative:
        number = -abs(number)
    return _format_number(number, decimals)


def _unify_decimal_separator(text: str) -> str:
    """Resolve '.' vs ',' by position: the rightmost separator with 1-2 trailing digits decides."""
    has_comma, has_dot = "," in text, "." in text
    if has_comma and has_dot:
        # Whichever comes last is the decimal point; the other is a thousands separator.
        if text.rfind(",") > text.rfind("."):
            return text.replace(".", "").replace(",", ".")
        return text.replace(",", "")
    if has_comma:
        # More than one separator of the same kind can only be thousands grouping -- a number
        # has at most one decimal point. "1,234,567" is unambiguous even though "1,234" is not.
        if text.count(",") > 1:
            return text.replace(",", "")
        tail = text.rsplit(",", 1)[1]
        # "1,234" is a thousands group; "1,23" and "1,2" are decimals.
        return text.replace(",", "") if len(tail) == 3 else text.replace(",", ".")
    if has_dot and text.count(".") > 1:
        # Same reasoning for the European convention: "1.234.567" is grouping, not decimals.
        # A lone "1.234" stays a decimal -- genuinely ambiguous, and the decimal reading is the
        # more common one worldwide.
        return text.replace(".", "")
    return text


def _format_number(number: float, decimals: int) -> str:
    text = f"{number:.{decimals}f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-", "-0") else text


def norm_quantity(value: Any) -> str:
    """A count. Whole numbers lose their decimal part so 12 and 12.0 agree."""
    normalised = norm_number(value, decimals=6)
    if normalised.endswith(".0"):
        return normalised[:-2]
    return normalised


#: Which normaliser each known field uses. `matching` and both readers share this table so the
#: two sides can never normalise the same field differently.
NORMALIZERS = {
    "date": norm_date,
    "description": norm_text,
    "quantity": norm_quantity,
    "amount": norm_number,
    "reference": norm_text,
    "account": norm_text,
}


def normalize_field(field_name: str, value: Any, date_order: str = DAY_FIRST) -> str:
    """Apply the normaliser registered for `field_name`, falling back to text."""
    if field_name == "date":
        return norm_date(value, date_order)
    return NORMALIZERS.get(field_name, norm_text)(value)


def mask_shape(text: str) -> str:
    """Show a token's shape only: digit->9, upper->A, lower->a, punctuation kept.

    Lets someone share what a document's structure looks like -- for a bug report, or to work
    out column positions with help -- without revealing a single real value.
    """
    return "".join(
        "9" if c.isdigit() else "A" if c.isupper() else "a" if c.islower() else c for c in text
    )
