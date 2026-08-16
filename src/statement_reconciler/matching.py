"""Match document records against spreadsheet records on a composite key.

Repeats are real: the same amount for the same thing can genuinely occur twice on one day, and
both sides will list it twice. So matching is multiset matching -- two document records sharing
a key consume two spreadsheet records, and a third on one side alone is reported as one-sided.
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
class Result:
    """Everything the report needs, and the verdict."""

    match_key: tuple[str, ...]
    matched: tuple[MatchedPair, ...]
    unmatched: tuple[Record, ...]
    unread_lines: tuple[str, ...] = ()

    @property
    def document_count(self) -> int:
        return len(self.matched) + sum(1 for r in self.unmatched if r.origin == DOCUMENT)

    @property
    def spreadsheet_count(self) -> int:
        return len(self.matched) + sum(1 for r in self.unmatched if r.origin == SPREADSHEET)

    @property
    def reconciled(self) -> bool:
        """Fully reconciled means: nothing one-sided, counts agree, and nothing left unread.

        Unread lines matter as much as mismatches. A line the reader could not interpret is not
        evidence of agreement -- it is a record nobody checked, and calling that "reconciled"
        would be the one failure mode that hides real breaks.
        """
        return (
            not self.unmatched
            and not self.unread_lines
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
        side = [p.document if origin == DOCUMENT else p.spreadsheet for p in self.matched]
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


def duplicate_keys(records: list[Record], match_key: tuple[str, ...]) -> dict[tuple[str, ...], int]:
    """Keys occurring more than once on one side.

    Not an error -- genuine repeats happen -- but worth surfacing, because a key that repeats a
    lot usually means the match key is too coarse to tell records apart.
    """
    counts = Counter(record.key(match_key) for record in records)
    return {key: count for key, count in counts.items() if count > 1}
