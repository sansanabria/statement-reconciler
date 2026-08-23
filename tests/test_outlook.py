"""Outlook tests run against fakes -- no COM, no mailbox, works on any platform."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from statement_reconciler.mail.naming import safe_filename, unique_name, weekdays
from statement_reconciler.mail.outlook import classify, fetch, resolve_folder

pytestmark = pytest.mark.unit


class FakeAttachment:
    def __init__(self, name: str, content: bytes = b"x" * 20000):
        self.FileName = name
        self._content = content
        self.Size = len(content)

    def SaveAsFile(self, path: str) -> None:
        Path(path).write_bytes(self._content)


class FakeMessage:
    def __init__(self, subject: str, received: datetime, attachments: list[FakeAttachment]):
        self.Subject = subject
        self.ReceivedTime = received
        self.Attachments = attachments


class FakeItems:
    def __init__(self, messages):
        self._messages = messages

    def Restrict(self, _query: str):
        return list(self._messages)

    def __iter__(self):
        return iter(self._messages)


class FakeFolder:
    def __init__(self, name: str, messages=(), children=()):
        self.Name = name
        self.Items = FakeItems(list(messages))
        self.Folders = list(children)


class FakeNamespace:
    def __init__(self, inbox: FakeFolder, roots=None):
        self._inbox = inbox
        self.Folders = roots if roots is not None else [inbox]

    def GetDefaultFolder(self, _id: int):
        return self._inbox


def message(subject="Daily Statement 02 March", name="daily_statement_01.pdf", size=20000):
    return FakeMessage(subject, datetime(2026, 3, 2, 8, 0), [FakeAttachment(name, b"x" * size)])


class TestClassify:
    def test_subject_route(self, config):
        assert classify(config, "Your Daily Statement", ()).name == "EXAMPLE_SOURCE"

    def test_attachment_route(self, config):
        assert classify(config, "FW: fyi", ("daily_statement_01.pdf",)) is not None

    def test_no_rule_matches(self, config):
        assert classify(config, "Lunch?", ("menu.pdf",)) is None


class TestResolveFolder:
    def test_walks_a_path(self):
        leaf = FakeFolder("Statements")
        namespace = FakeNamespace(FakeFolder("Inbox"), roots=[FakeFolder("Inbox", children=[leaf])])
        assert resolve_folder(namespace, "Inbox/Statements") is leaf

    def test_missing_folder_names_the_part(self):
        namespace = FakeNamespace(FakeFolder("Inbox"), roots=[FakeFolder("Inbox")])
        with pytest.raises(LookupError, match="no 'Absent'"):
            resolve_folder(namespace, "Inbox/Absent")

    def test_empty_path(self):
        with pytest.raises(ValueError, match="Empty mail folder path"):
            resolve_folder(FakeNamespace(FakeFolder("Inbox")), "  ")


class TestFetch:
    def test_dry_run_writes_nothing(self, config):
        namespace = FakeNamespace(FakeFolder("Inbox", [message()]))
        report = fetch(config, date(2026, 3, 2), date(2026, 3, 2), namespace)
        assert report.dry_run and not report.written
        assert report.messages_matched == 1
        assert not (config.output_root / "EXAMPLE_SOURCE").exists()

    def test_write_files_into_the_dated_folder(self, config):
        namespace = FakeNamespace(FakeFolder("Inbox", [message()]))
        report = fetch(config, date(2026, 3, 2), date(2026, 3, 2), namespace, dry_run=False)
        saved = report.written[0].path
        assert saved.exists()
        assert saved.parent.name == "EXAMPLE_SOURCE 2026.03.02"

    def test_unmatched_mail_is_ignored(self, config):
        namespace = FakeNamespace(FakeFolder("Inbox", [message(subject="Lunch?", name="menu.pdf")]))
        report = fetch(config, date(2026, 3, 2), date(2026, 3, 2), namespace, dry_run=False)
        assert report.messages_seen == 1 and report.messages_matched == 0

    def test_tiny_attachments_are_skipped(self, config):
        """Signature logos arrive as attachments; a 300-byte 'statement' is not one."""
        namespace = FakeNamespace(
            FakeFolder("Inbox", [message(name="daily_statement_logo.png", size=300)])
        )
        report = fetch(config, date(2026, 3, 2), date(2026, 3, 2), namespace, dry_run=False)
        assert not report.written
        assert "min_attachment_bytes" in report.skipped[0].skipped_reason

    def test_small_data_files_are_kept_anyway(self, config):
        namespace = FakeNamespace(
            FakeFolder("Inbox", [message(name="daily_statement.csv", size=50)])
        )
        report = fetch(config, date(2026, 3, 2), date(2026, 3, 2), namespace, dry_run=False)
        assert len(report.written) == 1

    def test_identical_resend_is_detected(self, config):
        """Same bytes under a different name is the same statement, not a second one."""
        first = message(name="daily_statement_01.pdf")
        second = message(subject="RESEND: Daily Statement", name="daily_statement_copy.pdf")
        namespace = FakeNamespace(FakeFolder("Inbox", [first, second]))
        report = fetch(config, date(2026, 3, 2), date(2026, 3, 2), namespace, dry_run=False)
        assert len(report.written) == 1
        assert report.skipped[0].duplicate_of is not None

    def test_only_filters_by_source(self, config):
        namespace = FakeNamespace(FakeFolder("Inbox", [message()]))
        report = fetch(config, date(2026, 3, 2), date(2026, 3, 2), namespace, only="OTHER")
        assert not report.saved

    def test_reversed_dates_rejected(self, config):
        namespace = FakeNamespace(FakeFolder("Inbox"))
        with pytest.raises(ValueError, match="before start date"):
            fetch(config, date(2026, 3, 5), date(2026, 3, 2), namespace)

    def test_configured_mail_folders_are_used(self, config_dict, tmp_path):
        from statement_reconciler.config import parse_config

        config_dict["output_root"] = str(tmp_path / "Statements")
        config_dict["mail_folders"] = ["Inbox/Statements"]
        config = parse_config(config_dict)
        leaf = FakeFolder("Statements", [message()])
        namespace = FakeNamespace(FakeFolder("Inbox"), roots=[FakeFolder("Inbox", children=[leaf])])
        report = fetch(config, date(2026, 3, 2), date(2026, 3, 2), namespace, dry_run=False)
        assert len(report.written) == 1

    def test_summary_reads_sensibly(self, config):
        namespace = FakeNamespace(FakeFolder("Inbox", [message()]))
        report = fetch(config, date(2026, 3, 2), date(2026, 3, 2), namespace)
        assert "1 of 1 messages matched" in report.summary()


class TestNaming:
    def test_illegal_characters_replaced(self):
        assert safe_filename("a/b:c*d.pdf") == "a_b_c_d.pdf"

    def test_empty_name_falls_back(self):
        assert safe_filename("   ") == "attachment"

    def test_unique_name_suffixes(self, tmp_path):
        (tmp_path / "a.pdf").write_text("x", encoding="utf-8")
        assert unique_name(tmp_path, "a.pdf").name == "a (2).pdf"

    def test_weekdays_skip_the_weekend(self):
        days = weekdays(date(2026, 3, 6), days=3)  # Friday
        assert [d.isoformat() for d in days] == ["2026-03-06", "2026-03-09", "2026-03-10"]
