"""Filenames and folder paths -- the single place both `fetch` and `inventory` agree on.

If these two disagreed, fetch would write into folders inventory never looks at, and the tool
would quietly report missing documents that are sitting on disk.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

from ..config import Config

# Characters Windows forbids in a filename, plus control characters.
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_filename(name: str, fallback: str = "attachment") -> str:
    """Make an attachment name safe to write, without changing its recognisable part."""
    cleaned = _ILLEGAL.sub("_", (name or "").strip()).strip(". ")
    return cleaned or fallback


def unique_name(folder: Path, filename: str) -> Path:
    """A path in `folder` that does not exist yet, suffixing ' (2)', ' (3)', ... as needed."""
    candidate = folder / safe_filename(filename)
    if not candidate.exists():
        return candidate
    stem, suffix = candidate.stem, candidate.suffix
    for counter in range(2, 1000):
        candidate = folder / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"Could not find a free name for {filename} in {folder}")


def run_folder(config: Config, source_name: str, when: date) -> Path:
    """Where one source's documents for one date are filed."""
    return config.folder_for(source_name, when)


def weekdays(start: date, days: int = 5) -> list[date]:
    """`days` weekdays starting at `start`, skipping Saturday and Sunday.

    Statements arrive on business days only; creating weekend folders makes the inventory
    report a missing document every Saturday forever.
    """
    result: list[date] = []
    cursor = start
    while len(result) < days:
        if cursor.weekday() < 5:
            result.append(cursor)
        cursor += timedelta(days=1)
    return result


def is_data_file(path: Path, config: Config) -> bool:
    return path.suffix.lower() in config.data_extensions


def is_document_file(path: Path) -> bool:
    return path.suffix.lower() == ".pdf"
