"""Command-line entry point: fetch | folders | check | inventory | probe."""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

from . import __version__
from .check import check_folder
from .config import Config, ConfigError, load_config
from .documents.pdf import probe_columns
from .inventory import scan
from .mail.naming import run_folder, weekdays


def _parse_date(text: str) -> date:
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a date in YYYY-MM-DD form") from None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reconcile",
        description="Fetch statement attachments from Outlook and cross-check PDF against "
        "spreadsheet.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subs = parser.add_subparsers(dest="command", required=True)

    def with_config(sub: argparse.ArgumentParser) -> argparse.ArgumentParser:
        sub.add_argument("--config", default="config.yaml", help="path to the YAML config")
        return sub

    fetch = with_config(subs.add_parser("fetch", help="save matching attachments from Outlook"))
    fetch.add_argument("--from", dest="start", type=_parse_date, required=True)
    fetch.add_argument("--to", dest="end", type=_parse_date, required=True)
    fetch.add_argument("--only", help="limit to one source by name")
    fetch.add_argument(
        "--write",
        action="store_true",
        help="actually save files. Without it, fetch only reports what it would do.",
    )

    folders = with_config(subs.add_parser("folders", help="create empty dated run folders"))
    folders.add_argument("--week", type=_parse_date, required=True, help="Monday of the week")
    folders.add_argument("--days", type=int, default=5, help="weekdays to create (default 5)")
    folders.add_argument("--only", help="limit to one source by name")

    check = with_config(subs.add_parser("check", help="reconcile one folder"))
    check.add_argument("folder", type=Path)
    check.add_argument("--source", help="source name, if it cannot be inferred from the path")
    check.add_argument("--no-report", action="store_true", help="print the result, write nothing")

    inventory = with_config(subs.add_parser("inventory", help="list folders missing a file"))
    inventory.add_argument("--from", dest="start", type=_parse_date, required=True)
    inventory.add_argument("--to", dest="end", type=_parse_date, required=True)
    inventory.add_argument("--only", help="limit to one source by name")
    inventory.add_argument("--all", action="store_true", help="list complete folders too")

    probe = subs.add_parser("probe", help="print a PDF page's words and x positions")
    probe.add_argument("pdf", type=Path)
    probe.add_argument("--page", type=int, default=1)
    probe.add_argument("--mask", action="store_true", help="show shapes only, hiding real values")

    return parser


def _date_range(start: date, end: date) -> list[date]:
    if end < start:
        raise ConfigError(f"--to {end} is before --from {start}")
    span = (end - start).days + 1
    return [d for d in weekdays(start, days=span) if d <= end]


def _cmd_fetch(args: argparse.Namespace, config: Config) -> int:
    from .mail.outlook import connect, fetch

    report = fetch(config, args.start, args.end, connect(), dry_run=not args.write, only=args.only)
    for item in report.saved:
        status = "SAVED" if item.written else f"skipped ({item.skipped_reason})"
        print(f"  [{item.source}] {item.filename} -> {item.path.parent}  {status}")
    print(report.summary())
    if not args.write:
        print("Dry run -- nothing was written. Re-run with --write to save these files.")
    return 0


def _cmd_folders(args: argparse.Namespace, config: Config) -> int:
    sources = [s for s in config.sources if not args.only or s.name.lower() == args.only.lower()]
    if not sources:
        raise ConfigError(f"No source named '{args.only}'")
    for when in weekdays(args.week, days=args.days):
        for source in sources:
            folder = run_folder(config, source.name, when)
            folder.mkdir(parents=True, exist_ok=True)
            print(f"  {folder}")
    return 0


def _cmd_check(args: argparse.Namespace, config: Config) -> int:
    source = config.source(args.source) if args.source else None
    result, out_path = check_folder(args.folder, config, source=source, write=not args.no_report)
    print(f"Document records:    {result.document_count}")
    print(f"Spreadsheet records: {result.spreadsheet_count}")
    print(f"Matched:             {len(result.matched)}")
    if result.match_on:
        print(f"Differing:           {len(result.differing)}")
    print(f"One-sided:           {len(result.unmatched)}")
    if result.ambiguous_ids:
        print(f"Ambiguous ids:       {', '.join(result.ambiguous_ids)}")
    print(f"Unread lines:        {len(result.unread_lines)}")
    print(f"Verdict:             {result.verdict}")
    if out_path:
        print(f"Report:              {out_path}")
    return 0 if result.reconciled else 1


def _cmd_inventory(args: argparse.Namespace, config: Config) -> int:
    statuses = scan(config, _date_range(args.start, args.end), only=args.only)
    shown = statuses if args.all else [s for s in statuses if not s.complete]
    for status in shown:
        flag = "OK     " if status.complete else "MISSING"
        print(f"  {flag} {status.source:<20} {status.missing:<22} {status.folder}")
    incomplete = sum(1 for s in statuses if not s.complete)
    print(f"{len(statuses)} folder(s) checked, {incomplete} incomplete.")
    return 0 if incomplete == 0 else 1


def _cmd_probe(args: argparse.Namespace) -> int:
    for line in probe_columns(args.pdf, page_number=args.page, mask=args.mask):
        print(line)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "probe":
            return _cmd_probe(args)
        config = load_config(args.config)
        handlers = {
            "fetch": _cmd_fetch,
            "folders": _cmd_folders,
            "check": _cmd_check,
            "inventory": _cmd_inventory,
        }
        return handlers[args.command](args, config)
    except (ConfigError, LookupError, ValueError, RuntimeError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
