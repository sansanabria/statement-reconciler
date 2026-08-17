"""Decide which document records and spreadsheet records are the same thing, and where they
disagree.

There are two ways to pair records, and which one applies depends on the documents:

**By identifier** (`reconcile_by_id`). Most transactional documents carry a reference that
appears on both sides -- an invoice number, a transaction id. Records pair on it, and then every
other field is compared. A wrong value is reported as exactly that: this record's amount differs.

**By composite key** (`reconcile`). Some documents carry no identifier at all. Then a record can
only be recognised by a combination of its own values, and a record whose amount differs is
indistinguishable from two unrelated records -- so it is reported as two one-sided rows rather
than one difference. That is not a limitation to work around; with nothing tying the rows
together, claiming they are the same record would be a guess, and a guess here hides which side
is wrong.

Repeats are real in both modes: the same amount for the same thing can genuinely occur twice,
and both sides will list it twice. So pairing is one-for-one -- two records sharing a key consume
two on the other side, and a third alone is reported.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from .records import DOCUMENT, SPREADSHEET, Record


@dataclass(frozen=True)
class MatchedPair:
    document: Record
    spreadsheet: Record


@dataclass(frozen=True)
class FieldDifference:
    """One field on which two paired records disagree."""

    field: str
    document_value: str
    spreadsheet_value: str


@dataclass(frozen=True)
class DifferingPair:
    """Two records that are the same record -- same identifier -- but do not agree."""

    identifier: str
    document: Record
    spreadsheet: Record
    differences: tuple[FieldDifference, ...]


@dataclass(frozen=True)
class Result:
    """Everything the report needs, and the verdict."""

    match_key: tuple[str, ...]
    matched: tuple[MatchedPair, ...]
    unmatched: tuple[Record, ...]
    unread_lines: tuple[str, ...] = ()
    #: Paired by identifier but disagreeing. Only ever populated in id mode -- without an
    #: identifier there is no way to know two differing records were meant to be the same one.
    differing: tuple[DifferingPair, ...] = ()
    #: Identifiers appearing more than once on a side. The pairing is then a guess about which
    #: copy goes with which, so it is surfaced rather than hidden.
    ambiguous_ids: tuple[str, ...] = ()
    #: The field records were paired on, when pairing by identifier.
    match_on: str | None = None

    @property
    def document_count(self) -> int:
        return (
            len(self.matched)
            + len(self.differing)
            + sum(1 for r in self.unmatched if r.origin == DOCUMENT)
        )

    @property
    def spreadsheet_count(self) -> int:
        return (
            len(self.matched)
            + len(self.differing)
            + sum(1 for r in self.unmatched if r.origin == SPREADSHEET)
        )

    @property
    def reconciled(self) -> bool:
        """Fully reconciled means: nothing one-sided, nothing disagreeing, nothing unread.

        Unread lines matter as much as mismatches. A line the reader could not interpret is not
        evidence of agreement -- it is a record nobody checked, and calling that "reconciled"
        would be the one failure mode that hides real breaks. An ambiguous identifier counts the
        same way: the pairing behind it was a guess.
        """
        return (
            not self.unmatched
            and not self.differing
            and not self.unread_lines
            and not self.ambiguous_ids
            and self.document_count == self.spreadsheet_count
        )

    @property
    def verdict(self) -> str:
        return "FULLY RECONCILED" if self.reconciled else "DIFFERENCES FOUND"

    def totals(self, field_name: str) -> tuple[float, float]:
        """Summed numeric value of `field_name` per side. Unparseable values count as zero."""
        return (
            _sum_field(self.records_for(DOCUMENT), field_name),
            _sum_field(self.records_for(SPREADSHEET), field_name),
        )

    def records_for(self, origin: str) -> tuple[Record, ...]:
        take_document = origin == DOCUMENT
        side = [p.document if take_document else p.spreadsheet for p in self.matched]
        side += [p.document if take_document else p.spreadsheet for p in self.differing]
        side += [r for r in self.unmatched if r.origin == origin]
        return tuple(side)


def _sum_field(records: tuple[Record, ...], field_name: str) -> float:
    total = 0.0
    for record in records:
        try:
            total += float(record.normalized(field_name))
        except ValueError:
            continue
    return total


def reconcile(
    document_records: list[Record],
    spreadsheet_records: list[Record],
    match_key: tuple[str, ...],
    unread_lines: tuple[str, ...] = (),
) -> Result:
    """Pair records by composite key; whatever is left over is one-sided."""
    if not match_key:
        raise ValueError("match_key is empty: records cannot be identified without one")

    pending: dict[tuple[str, ...], list[Record]] = defaultdict(list)
    for record in spreadsheet_records:
        pending[record.key(match_key)].append(record)

    matched: list[MatchedPair] = []
    unmatched: list[Record] = []
    for record in document_records:
        candidates = pending.get(record.key(match_key))
        if candidates:
            matched.append(MatchedPair(document=record, spreadsheet=candidates.pop(0)))
        else:
            unmatched.append(record)

    for leftovers in pending.values():
        unmatched.extend(leftovers)

    return Result(
        match_key=match_key,
        matched=tuple(matched),
        unmatched=tuple(unmatched),
        unread_lines=tuple(unread_lines),
    )


def reconcile_by_id(
    document_records: list[Record],
    spreadsheet_records: list[Record],
    match_on: str,
    compare_fields: tuple[str, ...],
    unread_lines: tuple[str, ...] = (),
) -> Result:
    """Pair records on a shared identifier, then compare every other field.

    A record found on both sides lands in `matched` if all compared fields agree, and in
    `differing` if they do not -- naming the field and both values, because with an identifier
    we know these two rows are the same record and can say precisely what is wrong with it.

    A record whose identifier is blank cannot be paired at all, so it is reported as one-sided
    rather than silently grouped with every other blank.
    """
    if not match_on:
        raise ValueError("match_on is empty: records cannot be paired without an identifier")
    if not compare_fields:
        raise ValueError(f"nothing to compare against '{match_on}': compare_fields is empty")

    pending: dict[str, list[Record]] = defaultdict(list)
    unmatched: list[Record] = []
    for record in spreadsheet_records:
        identifier = record.normalized(match_on)
        if identifier:
            pending[identifier].append(record)
        else:
            unmatched.append(record)

    ambiguous = {identifier for identifier, rows in pending.items() if len(rows) > 1}
    seen_on_document: Counter[str] = Counter()

    matched: list[MatchedPair] = []
    differing: list[DifferingPair] = []
    for record in document_records:
        identifier = record.normalized(match_on)
        if not identifier:
            unmatched.append(record)
            continue
        seen_on_document[identifier] += 1
        candidates = pending.get(identifier)
        if not candidates:
            unmatched.append(record)
            continue

        counterpart = candidates.pop(0)
        differences = compare(record, counterpart, compare_fields)
        if differences:
            differing.append(
                DifferingPair(
                    identifier=identifier,
                    document=record,
                    spreadsheet=counterpart,
                    differences=differences,
                )
            )
        else:
            matched.append(MatchedPair(document=record, spreadsheet=counterpart))

    for leftovers in pending.values():
        unmatched.extend(leftovers)
    ambiguous |= {identifier for identifier, n in seen_on_document.items() if n > 1}

    return Result(
        match_key=(match_on,),
        match_on=match_on,
        matched=tuple(matched),
        differing=tuple(differing),
        unmatched=tuple(unmatched),
        unread_lines=tuple(unread_lines),
        ambiguous_ids=tuple(sorted(ambiguous)),
    )


def compare(
    document: Record, spreadsheet: Record, fields: tuple[str, ...]
) -> tuple[FieldDifference, ...]:
    """Fields on which two paired records disagree, compared after normalisation.

    Comparison is on normalised values so that formatting -- 1,234.50 against 1234.5 -- is never
    reported as a difference, but the values shown are the originals, since that is what the
    reader will be looking at in the two files.
    """
    return tuple(
        FieldDifference(
            field=name,
            document_value=document.display(name),
            spreadsheet_value=spreadsheet.display(name),
        )
        for name in fields
        if document.normalized(name) != spreadsheet.normalized(name)
    )


def duplicate_keys(records: list[Record], match_key: tuple[str, ...]) -> dict[tuple[str, ...], int]:
    """Keys occurring more than once on one side.

    Not an error -- genuine repeats happen -- but worth surfacing, because a key that repeats a
    lot usually means the match key is too coarse to tell records apart.
    """
    counts = Counter(record.key(match_key) for record in records)
    return {key: count for key, count in counts.items() if count > 1}
