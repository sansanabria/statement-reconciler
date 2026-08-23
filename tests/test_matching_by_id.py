"""Pairing on a shared identifier, and reporting where paired records disagree."""

from __future__ import annotations

import pytest

from statement_reconciler.matching import compare, reconcile_by_id
from statement_reconciler.records import DOCUMENT, SPREADSHEET, Record

pytestmark = pytest.mark.unit

COMPARE = ("date", "description", "amount")


def doc(ref="INV-001", date_="2026-03-02", desc="ALPHA", amount="100.00"):
    values = {"reference": ref, "date": date_, "description": desc, "amount": amount}
    return Record(DOCUMENT, f"page 1, line {ref}", values)


def row(ref="INV-001", date_="2026-03-02", desc="ALPHA", amount="100.00"):
    values = {"reference": ref, "date": date_, "description": desc, "amount": amount}
    return Record(SPREADSHEET, f"row {ref}", values)


def run(documents, spreadsheets, unread=()):
    return reconcile_by_id(documents, spreadsheets, "reference", COMPARE, unread_lines=unread)


class TestAgreement:
    def test_same_id_and_same_values_reconciles(self):
        result = run([doc()], [row()])
        assert result.reconciled and len(result.matched) == 1
        assert not result.differing

    def test_formatting_alone_is_not_a_difference(self):
        result = run(
            [doc(date_="02-Mar-2026", amount="1,234.50")], [row(date_="2026-03-02", amount=1234.5)]
        )
        assert result.reconciled

    def test_match_on_is_recorded(self):
        assert run([doc()], [row()]).match_on == "reference"


class TestDifferences:
    def test_a_differing_amount_is_one_record_not_two(self):
        """The whole point of pairing on an id: name the field, do not hand back two mysteries."""
        result = run([doc(amount="100.00")], [row(amount="101.00")])
        assert not result.unmatched
        assert len(result.differing) == 1

        pair = result.differing[0]
        assert pair.identifier == "INV-001"
        assert [d.field for d in pair.differences] == ["amount"]
        assert pair.differences[0].document_value == "100.00"
        assert pair.differences[0].spreadsheet_value == "101.00"

    def test_differing_records_block_a_clean_verdict(self):
        assert not run([doc(amount="100.00")], [row(amount="101.00")]).reconciled

    def test_several_fields_differ_at_once(self):
        result = run([doc()], [row(desc="BETA", amount="101.00")])
        assert [d.field for d in result.differing[0].differences] == ["description", "amount"]

    def test_differing_records_still_count_on_both_sides(self):
        result = run([doc(amount="100.00")], [row(amount="101.00")])
        assert result.document_count == 1 and result.spreadsheet_count == 1

    def test_original_values_are_shown_not_normalised_ones(self):
        result = run([doc(amount="1,234.50")], [row(amount="1,243.50")])
        difference = result.differing[0].differences[0]
        assert difference.document_value == "1,234.50"


class TestOneSided:
    def test_id_only_in_the_document(self):
        result = run([doc(), doc(ref="INV-002")], [row()])
        assert [r.origin for r in result.unmatched] == [DOCUMENT]

    def test_id_only_in_the_spreadsheet(self):
        result = run([doc()], [row(), row(ref="INV-002")])
        assert [r.origin for r in result.unmatched] == [SPREADSHEET]

    def test_a_blank_identifier_cannot_be_paired(self):
        """Blank ids must not all collapse onto each other as if they were one record."""
        result = run([doc(ref="")], [row(ref="")])
        assert len(result.unmatched) == 2 and not result.matched


class TestAmbiguity:
    def test_a_repeated_id_is_flagged(self):
        result = run([doc(), doc()], [row(), row()])
        assert result.ambiguous_ids == ("INV-001",)
        assert not result.reconciled

    def test_repeated_on_the_spreadsheet_side_only(self):
        result = run([doc()], [row(), row()])
        assert result.ambiguous_ids == ("INV-001",)

    def test_unique_ids_are_never_ambiguous(self):
        assert not run([doc(), doc(ref="INV-002")], [row(), row(ref="INV-002")]).ambiguous_ids


class TestGuards:
    def test_empty_match_on(self):
        with pytest.raises(ValueError, match="match_on is empty"):
            reconcile_by_id([doc()], [row()], "", COMPARE)

    def test_nothing_to_compare(self):
        with pytest.raises(ValueError, match="nothing to compare"):
            reconcile_by_id([doc()], [row()], "reference", ())

    def test_unread_lines_still_block(self):
        assert not run([doc()], [row()], unread=("page 2: ???",)).reconciled

    def test_empty_inputs(self):
        assert run([], []).reconciled


class TestCompare:
    def test_returns_only_differing_fields(self):
        differences = compare(doc(), row(amount="101.00"), COMPARE)
        assert [d.field for d in differences] == ["amount"]

    def test_agreeing_records_give_nothing(self):
        assert compare(doc(), row(), COMPARE) == ()
