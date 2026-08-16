"""Pull attachments out of the Outlook desktop app and file them into dated folders.

Uses COM automation against the copy of classic Outlook you are already signed into. That means
no OAuth app registration, no client secret, no password stored anywhere -- which is usually the
only approach available on a locked-down corporate mailbox, and keeps the tool's data footprint
to files on your own disk.

Requires classic Outlook on Windows; the Microsoft Store "new Outlook" exposes no COM interface.

All COM access goes through the small protocols below, so every test injects fakes and no test
needs Outlook installed.
"""

from __future__ import annotations

import filecmp
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Protocol

from ..config import Config, Source
from .naming import run_folder, safe_filename, unique_name

# Outlook's Restrict() only understands its own locale-independent date literal format.
_RESTRICT_FORMAT = "%m/%d/%Y %H:%M %p"


class AttachmentLike(Protocol):
    FileName: str

    def SaveAsFile(self, path: str) -> None: ...


class MessageLike(Protocol):
    Subject: str
    ReceivedTime: Any
    Attachments: Any


@dataclass
class SavedFile:
    source: str
    subject: str
    filename: str
    path: Path
    written: bool
    skipped_reason: str = ""
    duplicate_of: Path | None = None


@dataclass
class FetchReport:
    """What a fetch did, or would have done in dry-run mode."""

    dry_run: bool
    saved: list[SavedFile] = field(default_factory=list)
    messages_seen: int = 0
    messages_matched: int = 0

    @property
    def written(self) -> list[SavedFile]:
        return [item for item in self.saved if item.written]

    @property
    def skipped(self) -> list[SavedFile]:
        return [item for item in self.saved if not item.written]

    def summary(self) -> str:
        action = "would save" if self.dry_run else "saved"
        return (
            f"{self.messages_matched} of {self.messages_seen} messages matched; "
            f"{action} {len(self.written)} file(s), skipped {len(self.skipped)}."
        )


def connect(dispatch: Any = None) -> Any:
    """Return the Outlook MAPI namespace. `dispatch` is injectable for tests."""
    if dispatch is None:  # pragma: no cover - requires Outlook on Windows
        try:
            import win32com.client
        except ImportError as exc:
            raise RuntimeError(
                "pywin32 is not installed. Fetching mail needs Windows with classic Outlook: "
                "pip install 'statement-reconciler[dev]' on Windows, or run `check` on files "
                "you have already downloaded."
            ) from exc
        dispatch = win32com.client.Dispatch
    return dispatch("Outlook.Application").GetNamespace("MAPI")


def resolve_folder(namespace: Any, path: str) -> Any:
    """Walk a 'Inbox/Statements' style path from the mailbox root."""
    parts = [part for part in path.replace("\\", "/").split("/") if part.strip()]
    if not parts:
        raise ValueError("Empty mail folder path")
    current = None
    for index, part in enumerate(parts):
        container = namespace.Folders if index == 0 else current.Folders
        current = _child_named(container, part)
        if current is None:
            raise LookupError(f"Outlook folder not found: {path} (no '{part}')")
    return current


def _child_named(container: Any, name: str) -> Any:
    for child in container:
        if str(child.Name).strip().lower() == name.strip().lower():
            return child
    return None


def _default_inbox(namespace: Any) -> Any:
    return namespace.GetDefaultFolder(6)  # olFolderInbox


def _restrict(items: Any, start: date, end: date) -> Any:
    """Narrow to a date range server-side. `end` is inclusive."""
    lower = datetime.combine(start, time.min).strftime(_RESTRICT_FORMAT)
    upper = datetime.combine(end + timedelta(days=1), time.min).strftime(_RESTRICT_FORMAT)
    return items.Restrict(f"[ReceivedTime] >= '{lower}' AND [ReceivedTime] < '{upper}'")


def _attachment_names(message: MessageLike) -> tuple[str, ...]:
    return tuple(str(att.FileName) for att in message.Attachments)


def _received_date(message: MessageLike) -> date:
    received = message.ReceivedTime
    if isinstance(received, datetime):
        return received.date()
    if isinstance(received, date):
        return received
    return datetime.fromisoformat(str(received)[:19]).date()


def classify(config: Config, subject: str, attachment_names: tuple[str, ...]) -> Source | None:
    """First source whose rule matches, or None."""
    for source in config.sources:
        if source.mail.matches(subject, attachment_names):
            return source
    return None


def _duplicate_of(candidate: Path, folder: Path) -> Path | None:
    """An identical file already filed elsewhere under the same root.

    Senders re-send the same statement, sometimes days later. Byte-comparing catches that even
    when the second copy arrives under a different filename.
    """
    root = folder.parent if folder.parent.exists() else folder
    for existing in root.rglob(f"*{candidate.suffix}"):
        if existing.is_file() and existing.stat().st_size == candidate.stat().st_size:
            if filecmp.cmp(existing, candidate, shallow=False):
                return existing
    return None


def _should_keep(name: str, size: int | None, config: Config) -> tuple[bool, str]:
    if Path(name).suffix.lower() in config.data_extensions:
        return True, ""
    if size is not None and size < config.min_attachment_bytes:
        return False, f"below min_attachment_bytes ({size} bytes)"
    return True, ""


def fetch(
    config: Config,
    start: date,
    end: date,
    namespace: Any,
    dry_run: bool = True,
    only: str | None = None,
) -> FetchReport:
    """Save matching attachments into their dated run folders.

    Defaults to a dry run: writing files pulled from a mailbox onto disk should be a deliberate
    choice, so the caller passes dry_run=False explicitly.
    """
    if end < start:
        raise ValueError(f"End date {end} is before start date {start}")

    folders = (
        [resolve_folder(namespace, path) for path in config.mail_folders]
        if config.mail_folders
        else [_default_inbox(namespace)]
    )
    report = FetchReport(dry_run=dry_run)

    for folder in folders:
        for message in _restrict(folder.Items, start, end):
            report.messages_seen += 1
            names = _attachment_names(message)
            source = classify(config, str(message.Subject or ""), names)
            if source is None or (only and source.name.lower() != only.lower()):
                continue
            report.messages_matched += 1
            _save_attachments(config, source, message, report, dry_run)

    return report


def _save_attachments(
    config: Config,
    source: Source,
    message: MessageLike,
    report: FetchReport,
    dry_run: bool,
) -> None:
    target = run_folder(config, source.name, _received_date(message))
    subject = str(message.Subject or "")

    for attachment in message.Attachments:
        name = safe_filename(str(attachment.FileName))
        size = getattr(attachment, "Size", None)
        keep, reason = _should_keep(name, size, config)
        if not keep:
            report.saved.append(SavedFile(source.name, subject, name, target / name, False, reason))
            continue

        if dry_run:
            report.saved.append(
                SavedFile(source.name, subject, name, target / name, False, "dry run")
            )
            continue

        target.mkdir(parents=True, exist_ok=True)
        destination = unique_name(target, name)
        attachment.SaveAsFile(str(destination))

        duplicate = _duplicate_of(destination, target)
        if duplicate is not None and duplicate != destination:
            destination.unlink()
            report.saved.append(
                SavedFile(
                    source.name,
                    subject,
                    name,
                    destination,
                    False,
                    "identical file already filed",
                    duplicate,
                )
            )
            continue

        report.saved.append(SavedFile(source.name, subject, name, destination, True))
