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


# --- id mode: the same documents, but carrying a reference on both sides -------------------

ID_COLUMN_X = {
    "reference": 40.0,
    "date": 110.0,
    "description": 190.0,
    "quantity": 340.0,
    "amount": 400.0,
}

ID_ROWS = [
    ("INV-001", "2026-03-02", "ALPHA WIDGET", "10", "1,234.50"),
    ("INV-002", "2026-03-02", "BETA GADGET", "4", "99.00"),
    ("INV-003", "2026-03-03", "GAMMA DEVICE", "25", "7,500.75"),
]

_ID_FIELDS = ("reference", "date", "description", "quantity", "amount")


@pytest.fixture
def id_config_dict(config_dict) -> dict:
    source = config_dict["sources"][0]
    source.pop("match_key")
    source["match_on"] = "reference"
    source["document"]["columns"] = dict(ID_COLUMN_X)
    source["records"] = {
        "reference": ["Reference", "Ref"],
        "date": ["Date"],
        "description": ["Description"],
        "quantity": ["Quantity"],
        "amount": ["Amount"],
    }
    return config_dict


@pytest.fixture
def id_config(id_config_dict, tmp_path):
    id_config_dict["output_root"] = str(tmp_path)
    return parse_config(id_config_dict)


@pytest.fixture
def make_id_run_folder(tmp_path):
    """A run folder whose documents both carry a reference column."""

    def _make(pdf_rows, xlsx_rows) -> Path:
        folder = tmp_path / "EXAMPLE_SOURCE" / "EXAMPLE_SOURCE 2026.03.02"
        folder.mkdir(parents=True, exist_ok=True)
        _write_pdf(folder / "statement.pdf", pdf_rows, columns=ID_COLUMN_X, fields=_ID_FIELDS)
        _write_xlsx(folder / "records.xlsx", xlsx_rows, headers=[f.title() for f in _ID_FIELDS])
        return folder

    return _make


def _write_pdf(
    path: Path,
    rows,
    columns=None,
    fields=("date", "description", "quantity", "amount"),
) -> None:
    columns = COLUMN_X if columns is None else columns
    reportlab = pytest.importorskip("reportlab", reason="reportlab builds the synthetic PDF")
    assert reportlab
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    page = canvas.Canvas(str(path), pagesize=A4)
    page.setFont("Helvetica", 9)
    height = A4[1]
    y = height - 60
    left = min(columns.values())
    page.drawString(left, y, "TRANSACTION DETAIL")
    y -= 20
    for row in rows:
        for field_name, value in zip(fields, row, strict=True):
            page.drawString(columns[field_name], y, value)
        y -= 16
    page.drawString(left, y - 10, "END OF REPORT")
    page.save()


def _write_xlsx(path: Path, rows, headers=("Date", "Description", "Quantity", "Amount")) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(list(headers))
    for row in rows:
        sheet.append(list(row))
    workbook.save(path)


@pytest.fixture
def run_folder(tmp_path) -> Path:
    """A folder holding a matching PDF and spreadsheet -- the clean, reconciled case."""
    folder = tmp_path / "EXAMPLE_SOURCE" / "EXAMPLE_SOURCE 2026.03.02"
    folder.mkdir(parents=True, exist_ok=True)
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
