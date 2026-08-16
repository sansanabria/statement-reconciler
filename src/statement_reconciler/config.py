"""Load and validate the YAML config.

Every domain fact the tool needs -- which mail to pick up, where to file it, how to read the
PDF, what the spreadsheet's columns are called, what makes two records the same -- is declared
here and nowhere else. The code contains no sender names, no column names, no folder names.

Validation is eager and loud: a typo in the config should fail at startup naming the offending
key, not surface three steps later as a confusing empty result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """A config file that cannot be used. The message always names the offending key."""


# Fields the tool understands. A source may use any subset; `match_key` may name any of them.
KNOWN_FIELDS = ("date", "description", "quantity", "amount", "reference", "account")

_MIN_ATTACHMENT_BYTES = 8 * 1024


def _require_mapping(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{where}: expected a mapping, got {type(value).__name__}")
    return value


def _reject_unknown(data: dict[str, Any], allowed: tuple[str, ...], where: str) -> None:
    unknown = sorted(set(data) - set(allowed))
    if unknown:
        raise ConfigError(
            f"{where}: unknown key(s) {', '.join(unknown)}. Allowed: {', '.join(sorted(allowed))}"
        )


def _str_list(value: Any, where: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"{where}: expected a string or a list of strings")
    return tuple(value)


@dataclass(frozen=True)
class MailRule:
    """How to recognise a message as belonging to a source.

    A message matches when EITHER every fragment in `subject_all` appears in the subject,
    OR any fragment in `attachment_contains` appears in an attachment filename. The second
    route matters because a forwarded message keeps the attachment but loses the subject.
    All comparisons are case-insensitive.
    """

    subject_all: tuple[str, ...] = ()
    attachment_contains: tuple[str, ...] = ()

    @staticmethod
    def from_dict(data: Any, where: str) -> MailRule:
        data = _require_mapping(data, where)
        _reject_unknown(data, ("subject_all", "attachment_contains"), where)
        rule = MailRule(
            subject_all=_str_list(data.get("subject_all"), f"{where}.subject_all"),
            attachment_contains=_str_list(
                data.get("attachment_contains"), f"{where}.attachment_contains"
            ),
        )
        if not rule.subject_all and not rule.attachment_contains:
            raise ConfigError(
                f"{where}: needs subject_all or attachment_contains, otherwise it matches nothing"
            )
        return rule

    def matches(self, subject: str, attachment_names: tuple[str, ...] = ()) -> bool:
        subject = (subject or "").lower()
        if self.subject_all and all(frag.lower() in subject for frag in self.subject_all):
            return True
        names = [n.lower() for n in attachment_names]
        return any(frag.lower() in name for frag in self.attachment_contains for name in names)


@dataclass(frozen=True)
class DocumentSpec:
    """How to read the PDF side.

    `columns` maps a field name to the x-coordinate where that column starts on the page.
    Words are assigned to the column whose start is the greatest one at or left of the word,
    which is how a value is recovered from a layout that has no ruled lines. Read
    `documents.pdf.probe_columns` to discover these numbers for a new layout.
    """

    columns: dict[str, float]
    start_markers: tuple[str, ...] = ()
    stop_markers: tuple[str, ...] = ()
    skip_markers: tuple[str, ...] = ()

    @staticmethod
    def from_dict(data: Any, where: str) -> DocumentSpec:
        data = _require_mapping(data, where)
        _reject_unknown(data, ("columns", "start_markers", "stop_markers", "skip_markers"), where)
        raw_columns = _require_mapping(data.get("columns"), f"{where}.columns")
        if not raw_columns:
            raise ConfigError(f"{where}.columns: at least one column is required")
        columns: dict[str, float] = {}
        for name, x in raw_columns.items():
            if name not in KNOWN_FIELDS:
                raise ConfigError(
                    f"{where}.columns.{name}: not a known field. "
                    f"Known fields: {', '.join(KNOWN_FIELDS)}"
                )
            if not isinstance(x, (int, float)) or isinstance(x, bool):
                raise ConfigError(f"{where}.columns.{name}: expected a number (the column's x0)")
            columns[name] = float(x)
        return DocumentSpec(
            columns=columns,
            start_markers=_str_list(data.get("start_markers"), f"{where}.start_markers"),
            stop_markers=_str_list(data.get("stop_markers"), f"{where}.stop_markers"),
            skip_markers=_str_list(data.get("skip_markers"), f"{where}.skip_markers"),
        )


@dataclass(frozen=True)
class RecordSpec:
    """How to read the spreadsheet side.

    Each field maps to a list of candidate column headers; the first one present in the file
    wins. Spreadsheet exports rename columns between versions, so listing the alternatives is
    cheaper than editing config every time.
    """

    aliases: dict[str, tuple[str, ...]]

    @staticmethod
    def from_dict(data: Any, where: str) -> RecordSpec:
        data = _require_mapping(data, where)
        aliases: dict[str, tuple[str, ...]] = {}
        for name, value in data.items():
            if name not in KNOWN_FIELDS:
                raise ConfigError(
                    f"{where}.{name}: not a known field. Known fields: {', '.join(KNOWN_FIELDS)}"
                )
            names = _str_list(value, f"{where}.{name}")
            if not names:
                raise ConfigError(f"{where}.{name}: needs at least one column name")
            aliases[name] = names
        if not aliases:
            raise ConfigError(f"{where}: at least one field is required")
        return RecordSpec(aliases=aliases)

    def pick_column(self, headers: tuple[str, ...], field_name: str) -> str:
        """Return the first configured alias present in `headers`.

        Raises with the full candidate list and the file's actual headers, so the fix is to
        paste the right name into the config -- no code change.
        """
        candidates = self.aliases.get(field_name, ())
        by_lower = {h.strip().lower(): h for h in headers}
        for candidate in candidates:
            hit = by_lower.get(candidate.strip().lower())
            if hit is not None:
                return hit
        raise ConfigError(
            f"No column found for '{field_name}'. Tried: {', '.join(candidates) or '(none)'}. "
            f"The file has: {', '.join(headers)}. Add the right name to records.{field_name}."
        )


@dataclass(frozen=True)
class Source:
    """One party that sends statements: how to recognise it, read it, and match its records."""

    name: str
    mail: MailRule
    document: DocumentSpec
    records: RecordSpec
    match_key: tuple[str, ...]

    @staticmethod
    def from_dict(data: Any, index: int) -> Source:
        where = f"sources[{index}]"
        data = _require_mapping(data, where)
        _reject_unknown(data, ("name", "match", "document", "records", "match_key"), where)

        name = data.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ConfigError(f"{where}.name: a non-empty name is required")
        where = f"sources[{name}]"

        document = DocumentSpec.from_dict(data.get("document"), f"{where}.document")
        records = RecordSpec.from_dict(data.get("records"), f"{where}.records")
        match_key = _str_list(data.get("match_key"), f"{where}.match_key")
        if not match_key:
            raise ConfigError(
                f"{where}.match_key: required. The two files share no record id, so records are "
                f"matched on a composite key -- list the fields that together identify a record."
            )
        for field_name in match_key:
            if field_name not in records.aliases:
                raise ConfigError(
                    f"{where}.match_key names '{field_name}', but records.{field_name} has no "
                    f"column names. Every match-key field must be readable from both sides."
                )
            if field_name not in document.columns:
                raise ConfigError(
                    f"{where}.match_key names '{field_name}', but document.columns has no "
                    f"'{field_name}'. Every match-key field must be readable from both sides."
                )
        return Source(
            name=name.strip(),
            mail=MailRule.from_dict(data.get("match"), f"{where}.match"),
            document=document,
            records=records,
            match_key=match_key,
        )


@dataclass(frozen=True)
class Config:
    """The whole config file."""

    output_root: Path
    folder_template: str
    sources: tuple[Source, ...]
    mail_folders: tuple[str, ...] = ()
    min_attachment_bytes: int = _MIN_ATTACHMENT_BYTES
    data_extensions: tuple[str, ...] = (".csv", ".xlsx", ".xlsm", ".ods", ".tsv")
    path: Path | None = field(default=None, compare=False)

    def source(self, name: str) -> Source:
        for src in self.sources:
            if src.name.lower() == name.lower():
                return src
        known = ", ".join(s.name for s in self.sources)
        raise ConfigError(f"No source named '{name}'. Configured sources: {known}")

    def folder_for(self, source_name: str, when: date) -> Path:
        """Render `folder_template` into an absolute path under `output_root`."""
        try:
            rendered = self.folder_template.format(source=source_name, date=when)
        except (KeyError, ValueError, IndexError) as exc:
            raise ConfigError(
                f"folder_template {self.folder_template!r} could not be rendered: {exc}. "
                f"Only {{source}} and {{date}} are available; use strftime codes on date, "
                f"e.g. {{date:%Y.%m.%d}}."
            ) from exc
        return self.output_root / rendered


_TOP_LEVEL = (
    "output_root",
    "folder_template",
    "sources",
    "mail_folders",
    "min_attachment_bytes",
    "data_extensions",
)


def load_config(path: str | Path) -> Config:
    """Read a YAML config file and validate it completely."""
    path = Path(path).expanduser()
    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: not valid YAML -- {exc}") from exc
    return parse_config(raw, path=path)


def parse_config(raw: Any, path: Path | None = None) -> Config:
    """Validate an already-loaded mapping. Split out from `load_config` so tests need no file."""
    data = _require_mapping(raw, "config")
    _reject_unknown(data, _TOP_LEVEL, "config")

    output_root = data.get("output_root")
    if not isinstance(output_root, str) or not output_root.strip():
        raise ConfigError("config.output_root: a path is required, e.g. '~/Statements'")

    folder_template = data.get("folder_template")
    if not isinstance(folder_template, str) or not folder_template.strip():
        raise ConfigError(
            "config.folder_template: required, e.g. '{source}/{source} {date:%Y.%m.%d}'"
        )

    raw_sources = data.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ConfigError("config.sources: at least one source is required")
    sources = tuple(Source.from_dict(s, i) for i, s in enumerate(raw_sources))

    seen: set[str] = set()
    for src in sources:
        key = src.name.lower()
        if key in seen:
            raise ConfigError(f"config.sources: duplicate source name '{src.name}'")
        seen.add(key)

    min_bytes = data.get("min_attachment_bytes", _MIN_ATTACHMENT_BYTES)
    if not isinstance(min_bytes, int) or isinstance(min_bytes, bool) or min_bytes < 0:
        raise ConfigError("config.min_attachment_bytes: expected a non-negative integer")

    extensions = _str_list(data.get("data_extensions"), "config.data_extensions")
    if not extensions:
        extensions = (".csv", ".xlsx", ".xlsm", ".ods", ".tsv")
    extensions = tuple(e if e.startswith(".") else f".{e}" for e in (x.lower() for x in extensions))

    config = Config(
        output_root=Path(output_root).expanduser(),
        folder_template=folder_template,
        sources=sources,
        mail_folders=_str_list(data.get("mail_folders"), "config.mail_folders"),
        min_attachment_bytes=min_bytes,
        data_extensions=extensions,
        path=path,
    )
    # Fail now rather than at fetch time if the template is malformed.
    config.folder_for(sources[0].name, date(2000, 1, 1))
    return config
