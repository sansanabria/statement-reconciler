"""Run one folder end to end: find the two files, read both, match, write the report."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import Config, ConfigError, Source
from .documents.pdf import read_pdf
from .documents.tabular import read_records
from .mail.naming import is_data_file, is_document_file
from .matching import Result, reconcile, reconcile_by_id
from .report import write_report

REPORT_NAME = "reconciliation_report.xlsx"


@dataclass(frozen=True)
class FolderFiles:
    document: Path
    spreadsheet: Path


def find_files(folder: Path, config: Config) -> FolderFiles:
    """Locate exactly one PDF and one spreadsheet in `folder`.

    Ambiguity is an error rather than a guess: picking the wrong one of two PDFs would produce
    a confident report about the wrong day.
    """
    if not folder.is_dir():
        raise ConfigError(f"Not a folder: {folder}")
    files = sorted(p for p in folder.iterdir() if p.is_file() and p.name != REPORT_NAME)
    documents = [p for p in files if is_document_file(p)]
    spreadsheets = [p for p in files if is_data_file(p, config)]

    for label, found in (("PDF", documents), ("spreadsheet", spreadsheets)):
        if not found:
            raise ConfigError(f"{folder}: no {label} found")
        if len(found) > 1:
            names = ", ".join(p.name for p in found)
            raise ConfigError(
                f"{folder}: {len(found)} {label} files found ({names}). "
                f"Leave exactly one of each in the folder, or point at a subfolder."
            )
    return FolderFiles(document=documents[0], spreadsheet=spreadsheets[0])


def infer_source(folder: Path, config: Config) -> Source:
    """Guess the source from the folder path, since the layout is named after it."""
    parts = [part.lower() for part in folder.resolve().parts]
    matches = [s for s in config.sources if any(s.name.lower() in part for part in parts)]
    if len(matches) == 1:
        return matches[0]
    if len(config.sources) == 1:
        return config.sources[0]
    known = ", ".join(s.name for s in config.sources)
    raise ConfigError(
        f"Could not tell which source {folder} belongs to. Pass --source. Configured: {known}"
    )


def check_folder(
    folder: Path, config: Config, source: Source | None = None, write: bool = True
) -> tuple[Result, Path | None]:
    """Reconcile one folder. Returns the result and where the report was written."""
    folder = Path(folder)
    source = source or infer_source(folder, config)
    files = find_files(folder, config)

    document_records, unread = read_pdf(files.document, source.document)
    spreadsheet_records = read_records(files.spreadsheet, source.records)

    if source.match_on:
        result = reconcile_by_id(
            document_records,
            spreadsheet_records,
            source.match_on,
            source.compare_fields,
            unread_lines=tuple(unread),
        )
    else:
        result = reconcile(
            document_records, spreadsheet_records, source.match_key, unread_lines=tuple(unread)
        )

    out_path = None
    if write:
        out_path = write_report(result, folder / REPORT_NAME, source.name, folder)
    return result, out_path
