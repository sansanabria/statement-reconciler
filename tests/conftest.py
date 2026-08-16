"""Synthetic fixtures. Every value here is invented -- no real document ever enters the repo."""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

from statement_reconciler.config import parse_config

# Column x positions the generated PDF is drawn at, reused by the config so the two agree.
COLUMN_X = {"date": 40.0, "description": 110.0, "quantity": 300.0, "amount": 380.0}

ROWS = [
    ("2026-03-02", "ALPHA WIDGET", "10", "1,234.50"),
    ("2026-03-02", "BETA GADGET", "4", "99.00"),
    ("2026-03-03", "GAMMA DEVICE", "25", "7,500.75"),
]


@pytest.fixture
def config_dict() -> dict:
    return {
        "output_root": "~/Statements",
        "folder_template": "{source}/{source} {date:%Y.%m.%d}",
        "sources": [
            {
                "name": "EXAMPLE_SOURCE",
                "match": {
                    "subject_all": ["Daily", "Statement"],
                    "attachment_contains": ["daily_statement"],
                },
                "document": {
                    "start_markers": ["TRANSACTION DETAIL"],
                    "stop_markers": ["END OF REPORT"],
                    "columns": dict(COLUMN_X),
                },
                "records": {
                    "date": ["Date", "Value Date"],
                    "description": ["Description", "Details"],
                    "quantity": ["Quantity", "Units"],
                    "amount": ["Amount", "Value"],
                },
                "match_key": ["date", "description", "amount", "quantity"],
            }
        ],
    }


@pytest.fixture
def config(config_dict, tmp_path):
    # output_root is tmp_path itself, so the `run_folder` fixture below lands exactly where
    # folder_template says it should -- inventory and fetch must agree on the layout.
    config_dict["output_root"] = str(tmp_path)
    return parse_config(config_dict)


@pytest.fixture
def source(config):
    return config.sources[0]


def _write_pdf(path: Path, rows: list[tuple[str, str, str, str]]) -> None:
    reportlab = pytest.importorskip("reportlab", reason="reportlab builds the synthetic PDF")
    assert reportlab
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    page = canvas.Canvas(str(path), pagesize=A4)
    page.setFont("Helvetica", 9)
    height = A4[1]
    y = height - 60
    page.drawString(COLUMN_X["date"], y, "TRANSACTION DETAIL")
    y -= 20
    for row in rows:
        fields = ("date", "description", "quantity", "amount")
        for field_name, value in zip(fields, row, strict=True):
            page.drawString(COLUMN_X[field_name], y, value)
        y -= 16
    page.drawString(COLUMN_X["date"], y - 10, "END OF REPORT")
    page.save()


def _write_xlsx(path: Path, rows: list[tuple[str, str, str, str]]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Date", "Description", "Quantity", "Amount"])
    for row in rows:
        sheet.append(list(row))
    workbook.save(path)


@pytest.fixture
def run_folder(tmp_path) -> Path:
    """A folder holding a matching PDF and spreadsheet -- the clean, reconciled case."""
    folder = tmp_path / "EXAMPLE_SOURCE" / "EXAMPLE_SOURCE 2026.03.02"
    folder.mkdir(parents=True)
    _write_pdf(folder / "statement.pdf", ROWS)
    _write_xlsx(folder / "records.xlsx", ROWS)
    return folder


@pytest.fixture
def make_run_folder(tmp_path):
    """Build a run folder with arbitrary rows per side, for the mismatch cases."""

    def _make(pdf_rows, xlsx_rows, name="EXAMPLE_SOURCE 2026.03.02") -> Path:
        folder = tmp_path / "EXAMPLE_SOURCE" / name
        folder.mkdir(parents=True, exist_ok=True)
        _write_pdf(folder / "statement.pdf", pdf_rows)
        _write_xlsx(folder / "records.xlsx", xlsx_rows)
        return folder

    return _make
