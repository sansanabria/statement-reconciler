"""Read records out of a PDF statement by word position.

The one rule that makes this work: use `extract_words()`, never `extract_text()`. A text dump
collapses empty columns, so a row with no quantity silently shifts its amount into the quantity
field and the reconciliation confirms a number that was never there. Word positions carry the
x-coordinate, so an empty column stays empty.

A line is the set of words sharing a rounded vertical position. Each word is assigned to the
column whose configured x0 is the greatest one at or left of the word's left edge.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pdfplumber

from ..config import DocumentSpec
from ..normalize import DAY_FIRST, mask_shape
from ..records import DOCUMENT, Record

# Words are grouped into a line by their rounded `top`. A tolerance of 1pt absorbs the sub-point
# baseline jitter of mixed font sizes without merging two genuinely adjacent rows.
_LINE_TOLERANCE = 1.0


def group_lines(words: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group a page's words into visual lines, each sorted left to right."""
    rows: dict[float, list[dict[str, Any]]] = {}
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        top = round(word["top"] / _LINE_TOLERANCE) * _LINE_TOLERANCE
        rows.setdefault(top, []).append(word)
    return [sorted(rows[top], key=lambda w: w["x0"]) for top in sorted(rows)]


def line_text(words: list[dict[str, Any]]) -> str:
    return " ".join(word["text"] for word in words)


def assign_columns(words: list[dict[str, Any]], columns: dict[str, float]) -> dict[str, str]:
    """Split one line's words into the configured columns by x position.

    A word belongs to the rightmost column that starts at or before it, with a small tolerance
    so a value nudged a point left of its header still lands in the right column. Words left of
    every column are dropped -- that is row furniture such as a bullet or a marker glyph.
    """
    ordered = sorted(columns.items(), key=lambda item: item[1])
    buckets: dict[str, list[str]] = {name: [] for name in columns}
    for word in words:
        target: str | None = None
        for name, x0 in ordered:
            if word["x0"] >= x0 - 2.0:
                target = name
            else:
                break
        if target is not None:
            buckets[target].append(word["text"])
    return {name: " ".join(parts) for name, parts in buckets.items()}


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in markers)


def read_pdf(
    path: str | Path, spec: DocumentSpec, date_order: str = DAY_FIRST
) -> tuple[list[Record], list[str]]:
    """Return (records, unread_lines).

    Unread lines are lines inside the record section that produced no value for any configured
    column. They are reported rather than dropped: a line nobody could read is not evidence of
    agreement, and it is the usual sign that the layout changed or a column x0 needs adjusting.
    """
    path = Path(path)
    records: list[Record] = []
    unread: list[str] = []
    # With no start marker, every line is in scope from the first page.
    in_section = not spec.start_markers

    with pdfplumber.open(str(path)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            for line_number, words in enumerate(group_lines(page.extract_words()), start=1):
                text = line_text(words)
                if not text.strip():
                    continue

                if not in_section:
                    if _contains_any(text, spec.start_markers):
                        in_section = True
                    continue
                if spec.stop_markers and _contains_any(text, spec.stop_markers):
                    in_section = False
                    continue
                if spec.skip_markers and _contains_any(text, spec.skip_markers):
                    continue
                # A line that repeats the start marker is the section header on a later page.
                if spec.start_markers and _contains_any(text, spec.start_markers):
                    continue

                values = assign_columns(words, spec.columns)
                if any(v.strip() for v in values.values()):
                    records.append(
                        Record(
                            origin=DOCUMENT,
                            locator=f"page {page_number}, line {line_number}",
                            values=values,
                            date_order=date_order,
                        )
                    )
                else:
                    unread.append(f"page {page_number}, line {line_number}: {text}")

    return records, unread


def probe_columns(path: str | Path, page_number: int = 1, mask: bool = False) -> list[str]:
    """Print-ready dump of a page's words and their x positions.

    This is how you find the numbers for `document.columns` on a layout you have not configured
    yet: look for where each column of values consistently begins. Pass mask=True to replace
    every character with its shape, so the output can be shared without exposing real values.
    """
    lines: list[str] = []
    with pdfplumber.open(str(Path(path))) as pdf:
        if not 1 <= page_number <= len(pdf.pages):
            raise ValueError(f"Page {page_number} is out of range (the PDF has {len(pdf.pages)})")
        page = pdf.pages[page_number - 1]
        for words in group_lines(page.extract_words()):
            parts = []
            for word in words:
                text = mask_shape(word["text"]) if mask else word["text"]
                parts.append(f"{text}@{word['x0']:.0f}")
            lines.append("  ".join(parts))
    return lines
