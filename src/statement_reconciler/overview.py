"""Reconcile a whole date range and summarise it in one workbook.

`check` answers "is this folder clean?". The question you actually ask each morning is "is this
week clean?", and answering it one folder at a time does not scale. This walks every source's
folder across a range, reconciles the ones that have both files, and writes a single overview:
one row per source per day, with the reason each red row is red.

One folder's failure never stops the walk. A missing file, an unreadable PDF or a config error
is recorded against that row and the range keeps going -- otherwise a single bad day would hide
the state of every other day.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .check import REPORT_NAME, check_folder
from .config import Config
from .inventory import inspect_folder
from .mail.naming import run_folder
from .matching import Result

#: Row states, worst first -- the order they are counted and reported in.
FAILED = "FAILED"
DIFFERENCES = "DIFFERENCES"
INCOMPLETE = "INCOMPLETE"
RECONCILED = "RECONCILED"

OVERVIEW_NAME = "overview.xlsx"


@dataclass(frozen=True)
class RunOutcome:
    """What happened for one source on one day."""

    source: str
    when: date
    folder: Path
    status: str
    result: Result | None = None
    note: str = ""

    @property
    def clean(self) -> bool:
        return self.status == RECONCILED

    @property
    def report_path(self) -> Path | None:
        path = self.folder / REPORT_NAME
        return path if path.is_file() else None


def run_range(
    config: Config, dates: list[date], only: str | None = None, write_reports: bool = True
) -> list[RunOutcome]:
    """Reconcile every source's folder for every date given."""
    sources = [s for s in config.sources if not only or s.name.lower() == only.lower()]
    outcomes: list[RunOutcome] = []
    for when in dates:
        for source in sources:
            folder = run_folder(config, source.name, when)
            outcomes.append(_run_one(config, source, when, folder, write_reports))
    return outcomes


def _run_one(config: Config, source, when: date, folder: Path, write_reports: bool) -> RunOutcome:
    status = inspect_folder(config, source.name, folder)
    if not status.complete:
        note = "folder does not exist" if not folder.is_dir() else f"missing {status.missing}"
        return RunOutcome(source.name, when, folder, INCOMPLETE, note=note)

    try:
        result, _ = check_folder(folder, config, source=source, write=write_reports)
    except Exception as exc:  # noqa: BLE001 - one bad folder must not stop the range
        return RunOutcome(source.name, when, folder, FAILED, note=f"{type(exc).__name__}: {exc}")

    state = RECONCILED if result.reconciled else DIFFERENCES
    return RunOutcome(source.name, when, folder, state, result=result, note=_reason(result))


def _reason(result: Result) -> str:
    """Why this row is not clean, in a few words -- the point of the overview."""
    if result.reconciled:
        return ""
    parts = []
    if result.warnings:
        # A warning means the comparison itself is untrustworthy, so it leads.
        parts.append("nothing read from document")
    if result.differing:
        parts.append(f"{len(result.differing)} differing")
    if result.unmatched:
        parts.append(f"{len(result.unmatched)} one-sided")
    if result.unread_lines:
        parts.append(f"{len(result.unread_lines)} unread")
    if result.ambiguous_ids:
        parts.append(f"{len(result.ambiguous_ids)} ambiguous id(s)")
    if not parts and result.document_count != result.spreadsheet_count:
        parts.append(f"counts differ ({result.document_count} vs {result.spreadsheet_count})")
    return ", ".join(parts)


def tally(outcomes: list[RunOutcome]) -> dict[str, int]:
    """Count per status, always including every status so a zero is visible as a zero."""
    counts = dict.fromkeys((RECONCILED, DIFFERENCES, INCOMPLETE, FAILED), 0)
    for outcome in outcomes:
        counts[outcome.status] += 1
    return counts
