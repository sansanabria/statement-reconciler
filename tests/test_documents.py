from __future__ import annotations

import pytest

from statement_reconciler.config import ConfigError, DocumentSpec
from statement_reconciler.documents.pdf import (
    assign_columns,
    group_lines,
    line_text,
    probe_columns,
    read_pdf,
)
from statement_reconciler.documents.tabular import read_records
from statement_reconciler.records import SPREADSHEET

pytestmark = pytest.mark.unit

COLUMNS = {"date": 40.0, "description": 110.0, "quantity": 300.0, "amount": 380.0}


def word(text, x0, top=100.0):
    return {"text": text, "x0": x0, "x1": x0 + 20, "top": top, "bottom": top + 9}


class TestGrouping:
    def test_words_group_into_lines_left_to_right(self):
        words = [word("B", 60, 100), word("A", 20, 100), word("C", 20, 130)]
        lines = group_lines(words)
        assert [line_text(line) for line in lines] == ["A B", "C"]

    def test_sub_point_jitter_stays_one_line(self):
        lines = group_lines([word("A", 20, 100.0), word("B", 60, 100.4)])
        assert len(lines) == 1

    def test_no_words_gives_no_lines(self):
        assert group_lines([]) == []


class TestColumnAssignment:
    def test_words_land_in_their_column(self):
        line = [word("2026-03-02", 40), word("ALPHA", 110), word("WIDGET", 150), word("10", 300)]
        assert assign_columns(line, COLUMNS) == {
            "date": "2026-03-02",
            "description": "ALPHA WIDGET",
            "quantity": "10",
            "amount": "",
        }

    def test_an_empty_column_stays_empty(self):
        """The reason word positions are used at all: a blank column must not shift values."""
        line = [word("2026-03-02", 40), word("ALPHA", 110), word("99.00", 380)]
        assigned = assign_columns(line, COLUMNS)
        assert assigned["quantity"] == "" and assigned["amount"] == "99.00"

    def test_slight_left_nudge_still_lands_right(self):
        assert assign_columns([word("10", 298.5)], COLUMNS)["quantity"] == "10"

    def test_words_left_of_every_column_are_dropped(self):
        assert assign_columns([word("*", 5)], COLUMNS) == dict.fromkeys(COLUMNS, "")


class TestReadPdf:
    def test_reads_the_rows_between_the_markers(self, run_folder, source):
        records, unread = read_pdf(run_folder / "statement.pdf", source.document)
        assert not unread
        assert [r.values["description"] for r in records] == [
            "ALPHA WIDGET",
            "BETA GADGET",
            "GAMMA DEVICE",
        ]
        assert records[0].values["amount"] == "1,234.50"
        assert records[0].locator.startswith("page 1")

    def test_marker_lines_are_not_records(self, run_folder, source):
        records, _ = read_pdf(run_folder / "statement.pdf", source.document)
        joined = " ".join(str(r.values) for r in records)
        assert "TRANSACTION DETAIL" not in joined and "END OF REPORT" not in joined

    def test_without_a_start_marker_every_line_is_read(self, run_folder):
        spec = DocumentSpec(columns=COLUMNS)
        records, _ = read_pdf(run_folder / "statement.pdf", spec)
        assert len(records) == 5  # 3 rows plus both marker lines

    def test_skip_markers_drop_page_furniture(self, run_folder):
        spec = DocumentSpec(columns=COLUMNS, skip_markers=("BETA",))
        records, _ = read_pdf(run_folder / "statement.pdf", spec)
        assert all("BETA" not in r.values["description"] for r in records)

    def test_lines_outside_every_column_are_reported_unread(self, run_folder):
        """Columns far right of the text: nothing lands, so every line is flagged, not dropped."""
        spec = DocumentSpec(columns={"amount": 5000.0})
        records, unread = read_pdf(run_folder / "statement.pdf", spec)
        assert not records and unread


class TestProbe:
    def test_probe_shows_positions(self, run_folder):
        lines = probe_columns(run_folder / "statement.pdf")
        assert any("TRANSACTION" in line and "@" in line for line in lines)

    def test_masked_probe_reveals_no_values(self, run_folder):
        lines = probe_columns(run_folder / "statement.pdf", mask=True)
        assert not any("ALPHA" in line for line in lines)
        assert any("AAAAA" in line for line in lines)

    def test_page_out_of_range(self, run_folder):
        with pytest.raises(ValueError, match="out of range"):
            probe_columns(run_folder / "statement.pdf", page_number=9)


class TestReadRecords:
    def test_reads_every_row(self, run_folder, source):
        records = read_records(run_folder / "records.xlsx", source.records)
        assert len(records) == 3
        assert records[0].origin == SPREADSHEET
        assert records[0].locator == "row 2"
        assert records[0].values["description"] == "ALPHA WIDGET"

    def test_missing_column_error_is_actionable(self, run_folder, source, tmp_path):
        from openpyxl import Workbook

        path = tmp_path / "wrong.xlsx"
        workbook = Workbook()
        workbook.active.append(["Booking Day", "Description", "Quantity", "Amount"])
        workbook.save(path)
        with pytest.raises(ConfigError) as excinfo:
            read_records(path, source.records)
        assert "date" in str(excinfo.value) and "Booking Day" in str(excinfo.value)

    def test_unsupported_type(self, tmp_path, source):
        path = tmp_path / "notes.docx"
        path.write_text("x", encoding="utf-8")
        with pytest.raises(ConfigError, match="unsupported spreadsheet type"):
            read_records(path, source.records)

    def test_csv_is_supported(self, tmp_path, source):
        path = tmp_path / "records.csv"
        path.write_text(
            "Date,Description,Quantity,Amount\n2026-03-02,ALPHA WIDGET,10,1234.50\n",
            encoding="utf-8",
        )
        assert len(read_records(path, source.records)) == 1

    def test_blank_rows_are_skipped(self, tmp_path, source):
        path = tmp_path / "records.csv"
        path.write_text(
            "Date,Description,Quantity,Amount\n2026-03-02,ALPHA,10,1\n,,,\n", encoding="utf-8"
        )
        assert len(read_records(path, source.records)) == 1
