"""Read records out of a spreadsheet (xlsx / xlsm / ods / csv / tsv).

Columns are resolved through the config's alias lists rather than fixed names, because exports
rename their headers between versions. When no alias matches, the error names the field, every
alias tried, and the file's real headers -- so the fix is a config edit, never a code edit.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..config import ConfigError, RecordSpec
from ..records import SPREADSHEET, Record

_EXCEL_SUFFIXES = {".xlsx", ".xlsm", ".xltx", ".xltm"}
_ODS_SUFFIXES = {".ods"}
_DELIMITED = {".csv": ",", ".tsv": "\t", ".txt": None}


def read_table(path: str | Path) -> pd.DataFrame:
    """Load any supported tabular file into a DataFrame, everything as text."""
    path = Path(path)
    suffix = path.suffix.lower()
    # dtype=str keeps a reference like "007" from becoming 7, and leaves every value exactly as
    # written for the normalisers to canonicalise.
    if suffix in _EXCEL_SUFFIXES:
        return pd.read_excel(path, dtype=str, engine="openpyxl")
    if suffix in _ODS_SUFFIXES:
        return pd.read_excel(path, dtype=str, engine="odf")
    if suffix in _DELIMITED:
        return pd.read_csv(path, dtype=str, sep=_DELIMITED[suffix], engine="python")
    raise ConfigError(
        f"{path.name}: unsupported spreadsheet type '{suffix}'. "
        f"Supported: {', '.join(sorted(_EXCEL_SUFFIXES | _ODS_SUFFIXES | set(_DELIMITED)))}"
    )


def read_records(path: str | Path, spec: RecordSpec) -> list[Record]:
    """Read a spreadsheet into Records, one per non-empty row."""
    path = Path(path)
    frame = read_table(path)
    headers = tuple(str(column) for column in frame.columns)
    resolved = {name: spec.pick_column(headers, name) for name in spec.aliases}

    records: list[Record] = []
    for position, (_, row) in enumerate(frame.iterrows(), start=2):  # row 1 is the header
        values = {
            name: ("" if pd.isna(row[column]) else row[column]) for name, column in resolved.items()
        }
        if not any(str(value).strip() for value in values.values()):
            continue
        records.append(Record(origin=SPREADSHEET, locator=f"row {position}", values=values))
    return records
