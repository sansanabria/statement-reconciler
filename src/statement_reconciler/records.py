"""The one record type both readers produce, and the composite key built from it."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .normalize import DAY_FIRST, normalize_field

DOCUMENT = "document"
SPREADSHEET = "spreadsheet"


@dataclass(frozen=True)
class Record:
    """One row, from either side, with its raw values kept for the report.

    `origin` says which side it came from and `locator` says where (a page and line number, or
    a spreadsheet row number) so an unmatched record can be found in the source file by hand.
    """

    origin: str
    locator: str
    values: dict[str, Any] = field(default_factory=dict)
    #: How to read an ambiguous numeric date. Carried on the record rather than passed at match
    #: time so the two sides of one source can never be normalised with different rules.
    date_order: str = DAY_FIRST

    def normalized(self, field_name: str) -> str:
        return normalize_field(field_name, self.values.get(field_name), self.date_order)

    def key(self, match_key: tuple[str, ...]) -> tuple[str, ...]:
        """The composite key. The two files share no record id, so identity is a field tuple."""
        return tuple(self.normalized(name) for name in match_key)

    def display(self, field_name: str) -> str:
        value = self.values.get(field_name)
        return "" if value is None else str(value)
