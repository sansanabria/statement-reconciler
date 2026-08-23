from __future__ import annotations

import pytest

from statement_reconciler.matching import duplicate_keys, reconcile
from statement_reconciler.records import DOCUMENT, SPREADSHEET, Record

pytestmark = pytest.mark.unit

KEY = ("date", "description", "amount")


def doc(date_="2026-03-02", desc="ALPHA", amount="100.00", **extra):
    return Record(
        DOCUMENT, "page 1", {"date": date_, "description": desc, "amount": amount, **extra}
    )


def row(date_="2026-03-02", desc="ALPHA", amount="100.00", **extra):
    return Record(
        SPREADSHEET, "row 2", {"date": date_, "description": desc, "amount": amount, **extra}
    )


def test_identical_records_reconcile():
    result = reconcile([doc()], [row()], KEY)
    assert result.reconciled
    assert result.verdict == "FULLY RECONCILED"
    assert len(result.matched) == 1 and not result.unmatched


def test_matches_across_different_spellings():
    """The whole point of normalising: the two sides never write a value the same way."""
    result = reconcile(
        [doc(date_="02-Mar-2026", amount="1,234.50")],
        [row(date_="2026-03-02", amount=1234.5)],
        KEY,
    )
    assert result.reconciled


def test_record_only_in_document():
    result = reconcile([doc(), doc(desc="BETA")], [row()], KEY)
    assert not result.reconciled
    assert [r.origin for r in result.unmatched] == [DOCUMENT]
    assert result.document_count == 2 and result.spreadsheet_count == 1


def test_record_only_in_spreadsheet():
    result = reconcile([doc()], [row(), row(desc="BETA")], KEY)
    assert [r.origin for r in result.unmatched] == [SPREADSHEET]


def test_amount_difference_shows_as_two_one_sided_records():
    """No shared id exists, so a changed amount is a break on both sides, not an edit."""
    result = reconcile([doc(amount="100.00")], [row(amount="101.00")], KEY)
    assert len(result.unmatched) == 2
    assert {r.origin for r in result.unmatched} == {DOCUMENT, SPREADSHEET}


def test_genuine_repeats_are_matched_one_for_one():
    result = reconcile([doc(), doc()], [row(), row()], KEY)
    assert len(result.matched) == 2 and result.reconciled


def test_a_third_repeat_on_one_side_is_one_sided():
    result = reconcile([doc(), doc(), doc()], [row(), row()], KEY)
    assert len(result.matched) == 2
    assert len(result.unmatched) == 1 and result.unmatched[0].origin == DOCUMENT


def test_records_differing_only_outside_the_key_still_match():
    result = reconcile([doc(account="A")], [row(account="B")], KEY)
    assert result.reconciled


def test_unread_lines_block_a_clean_verdict():
    """A line nobody could read is not evidence of agreement."""
    result = reconcile([doc()], [row()], KEY, unread_lines=("page 2, line 9: ???",))
    assert not result.reconciled
    assert result.verdict == "DIFFERENCES FOUND"


def test_empty_inputs_reconcile_trivially():
    result = reconcile([], [], KEY)
    assert result.reconciled and result.document_count == 0


def test_empty_match_key_is_rejected():
    with pytest.raises(ValueError, match="match_key is empty"):
        reconcile([doc()], [row()], ())


def test_totals_ignore_unparseable_values():
    result = reconcile([doc(amount="1,000.00"), doc(amount="n/a")], [row(amount="1000")], KEY)
    doc_total, sheet_total = result.totals("amount")
    assert doc_total == 1000.0 and sheet_total == 1000.0


def test_duplicate_keys_reports_repeats_only():
    assert duplicate_keys([doc(), doc(), doc(desc="BETA")], KEY) == {
        ("2026-03-02", "ALPHA", "100"): 2
    }


def test_records_for_covers_both_matched_and_unmatched():
    result = reconcile([doc(), doc(desc="BETA")], [row()], KEY)
    assert len(result.records_for(DOCUMENT)) == 2
    assert len(result.records_for(SPREADSHEET)) == 1


class TestRepeatedKeysAreReported:
    """Repeats are legitimate, but a key that repeats a lot is too coarse to be trusted."""

    def test_a_repeated_key_is_surfaced(self):
        result = reconcile([doc(), doc()], [row(), row()], KEY)
        assert result.repeated_keys
        assert "x2" in result.repeated_keys[0]

    def test_repeats_still_reconcile(self):
        """Reporting them must not turn a legitimate repeat into a failure."""
        assert reconcile([doc(), doc()], [row(), row()], KEY).reconciled

    def test_unique_keys_report_nothing(self):
        assert reconcile([doc()], [row()], KEY).repeated_keys == ()

    def test_a_repeat_on_one_side_only_is_still_shown(self):
        result = reconcile([doc(), doc()], [row()], KEY)
        assert result.repeated_keys and not result.reconciled
