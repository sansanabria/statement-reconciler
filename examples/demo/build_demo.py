"""Generate a working demo: a statement PDF, a spreadsheet, and a config that ties them together.

Run this to see what the tool actually produces without needing documents of your own:

    python examples/demo/build_demo.py
    reconcile check --config demo/config.yaml "demo/ACME_SUPPLIES/ACME_SUPPLIES 2026.03.02"

The generated week contains one deliberate example of each thing that can go wrong, so the
report has something to show. Everything here is invented.

Needs reportlab, which comes with the dev extras: pip install -e ".[dev]"
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import yaml
from openpyxl import Workbook

# Where each column is drawn on the page, and therefore what goes in document.columns.
COLUMNS = {
    "reference": 45.0,
    "date": 130.0,
    "description": 210.0,
    "quantity": 360.0,
    "amount": 420.0,
}
FIELDS = ("reference", "date", "description", "quantity", "amount")
HEADERS = ["Reference", "Date", "Description", "Quantity", "Amount"]

SOURCE = "ACME_SUPPLIES"

# What the supplier's statement says.
STATEMENT = [
    ("INV-4471", "02-Mar-2026", "Copier paper A4", "40", "1,234.50"),
    ("INV-4472", "02-Mar-2026", "Toner cartridges", "6", "899.00"),
    ("INV-4473", "02-Mar-2026", "Desk risers", "12", "540.00"),
    ("INV-4474", "02-Mar-2026", "Cable trays", "30", "275.25"),
]

# What your own ledger says. Three deliberate discrepancies against the statement above:
#   INV-4472  amount transposed -- 899.00 on the statement, 989.00 here
#   INV-4474  missing entirely  -- the supplier billed it, you never booked it
#   INV-4480  booked but not on the supplier's statement at all
LEDGER = [
    ("INV-4471", "2026-03-02", "Copier paper A4", "40", "1234.50"),
    ("INV-4472", "2026-03-02", "Toner cartridges", "6", "989.00"),
    ("INV-4473", "2026-03-02", "Desk risers", "12", "540.00"),
    ("INV-4480", "2026-03-02", "Whiteboard markers", "50", "62.00"),
]


def write_pdf(path: Path, rows) -> None:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except ImportError:
        sys.exit("reportlab is needed to draw the demo statement.\n" '  pip install -e ".[dev]"')

    page = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    y = height - 60

    page.setFont("Helvetica-Bold", 13)
    page.drawString(COLUMNS["reference"], y, "ACME SUPPLIES LTD")
    y -= 16
    page.setFont("Helvetica", 9)
    page.drawString(COLUMNS["reference"], y, "Statement of account -- 2 March 2026")
    y -= 30

    page.setFont("Helvetica-Bold", 9)
    page.drawString(COLUMNS["reference"], y, "TRANSACTION DETAIL")
    y -= 14
    for field_name in FIELDS:
        page.drawString(COLUMNS[field_name], y, field_name.title())
    y -= 4
    page.line(COLUMNS["reference"], y, width - 50, y)
    y -= 14

    page.setFont("Helvetica", 9)
    for row in rows:
        for field_name, value in zip(FIELDS, row, strict=True):
            page.drawString(COLUMNS[field_name], y, value)
        y -= 16

    y -= 10
    page.setFont("Helvetica-Bold", 9)
    page.drawString(COLUMNS["reference"], y, "END OF REPORT")
    page.save()


def write_xlsx(path: Path, rows) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Ledger"
    sheet.append(HEADERS)
    for row in rows:
        sheet.append(list(row))
    workbook.save(path)


def build_config(root: Path) -> dict:
    return {
        "output_root": str(root),
        "folder_template": "{source}/{source} {date:%Y.%m.%d}",
        "mail_folders": ["Inbox"],
        "sources": [
            {
                "name": SOURCE,
                "match": {
                    "subject_all": ["Statement", "Acme"],
                    "attachment_contains": ["acme_statement"],
                },
                "document": {
                    "start_markers": ["TRANSACTION DETAIL"],
                    "stop_markers": ["END OF REPORT"],
                    "skip_markers": ["Reference Date Description"],
                    "columns": dict(COLUMNS),
                },
                "records": {
                    "reference": ["Reference", "Ref", "Invoice No"],
                    "date": ["Date", "Invoice Date"],
                    "description": ["Description", "Details"],
                    "quantity": ["Quantity", "Units"],
                    "amount": ["Amount", "Value", "Total"],
                },
                "match_on": "reference",
            }
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a runnable demo for statement-reconciler.")
    parser.add_argument("--out", type=Path, default=Path("demo"), help="where to write (./demo)")
    parser.add_argument("--force", action="store_true", help="overwrite an existing demo folder")
    args = parser.parse_args(argv)

    root = args.out.expanduser().resolve()
    if root.exists():
        if not args.force:
            sys.exit(f"{root} already exists. Pass --force to replace it.")
        shutil.rmtree(root)

    folder = root / SOURCE / f"{SOURCE} 2026.03.02"
    folder.mkdir(parents=True)
    write_pdf(folder / "acme_statement_2026-03-02.pdf", STATEMENT)
    write_xlsx(folder / "ledger_export.xlsx", LEDGER)
    (root / "config.yaml").write_text(yaml.safe_dump(build_config(root), sort_keys=False), "utf-8")

    print(f"Demo written to {root}\n")
    print("Now run:\n")
    print(f'  reconcile check --config "{root / "config.yaml"}" "{folder}"\n')
    print("Expected: one differing record (INV-4472), one billed but not booked (INV-4474),")
    print("and one booked but not billed (INV-4480).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
