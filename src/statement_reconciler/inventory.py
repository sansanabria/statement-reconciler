"""Which run folders are incomplete.

A reconciliation needs both sides. This answers the question you ask before starting work --
"has everything arrived?" -- by looking at the filesystem only. No mailbox, no parsing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .mail.naming import is_data_file, is_document_file, run_folder


@dataclass(frozen=True)
class FolderStatus:
    source: str
    folder: Path
    has_document: bool
    has_data: bool

    @property
    def complete(self) -> bool:
        return self.has_document and self.has_data

    @property
    def missing(self) -> str:
        gaps = []
        if not self.has_document:
            gaps.append("PDF")
        if not self.has_data:
            gaps.append("spreadsheet")
        return " + ".join(gaps) or "-"


def inspect_folder(config: Config, source_name: str, folder: Path) -> FolderStatus:
    files = [p for p in folder.iterdir() if p.is_file()] if folder.is_dir() else []
    return FolderStatus(
        source=source_name,
        folder=folder,
        has_document=any(is_document_file(p) for p in files),
        has_data=any(is_data_file(p, config) for p in files),
    )


def scan(config: Config, dates: list, only: str | None = None) -> list[FolderStatus]:
    """Status of every source's folder for each date given, expected folders included.

    A folder that was never created is reported as missing both sides -- that is the case that
    matters most, and skipping non-existent paths would hide it.
    """
    sources = [s for s in config.sources if not only or s.name.lower() == only.lower()]
    return [
        inspect_folder(config, source.name, run_folder(config, source.name, when))
        for when in dates
        for source in sources
    ]
