# statement-reconciler

Pull statement attachments out of Outlook, file them into dated folders on your computer, and
cross-check the PDF statement against the spreadsheet that is supposed to say the same thing.

Someone sends you a PDF statement. Your own system exports a spreadsheet of the same records.
The two should agree, and checking them by eye is slow and easy to get wrong. This tool does the
comparison and writes an Excel report saying what matched, what did not, and which side is
missing what.

Everything runs locally on your machine. Nothing is uploaded anywhere, and there is no AI in the


## Install

Requires Python 3.11+. Fetching mail additionally requires Windows with the **classic** Outlook
desktop app -- the Microsoft Store "new Outlook" exposes no automation interface. The `check`
and `inventory` commands work on any platform, on files you already have.

```bash
git clone <this repo>
cd statement-reconciler
python -m venv .venv
.venv/Scripts/activate        # Windows;  source .venv/bin/activate elsewhere
pip install -e ".[dev]"
```

## Setup

```bash
cp config.example.yaml config.yaml
```

Then edit `config.yaml`. It is commented throughout; the four things to get right are:

**0. How records pair up.** If both files carry a shared reference, set `match_on` to that field
— you get far better reports. If they don't, use `match_key` instead. See
[How the comparison works](#how-the-comparison-works).

**1. How to recognise the mail.** A message matches a source if every fragment in `subject_all`
appears in the subject, *or* any fragment in `attachment_contains` appears in an attachment
filename. The second route is what catches a forwarded message, which keeps the file but loses
the original subject wording.

**2. Where the PDF's columns are.** Run:

```bash
reconcile probe statement.pdf --mask
```

That prints each word on page 1 with the x position it sits at, e.g. `AAAAA@110`. Look down the
page for where each column of values consistently starts and put those numbers into
`document.columns`. `--mask` replaces every character with its shape (`9` for a digit, `A` for an
uppercase letter), so you can share the output to get help without exposing any real value.

**3. What your spreadsheet calls each field.** Under `records`, list the possible column headers
for each field -- first one present in the file wins. If none match, the error tells you what it
tried and what the file actually has, so the fix is a config edit rather than a code change.

## Use

```bash
# See what would be downloaded. Writes nothing.
reconcile fetch --from 2026-03-02 --to 2026-03-06

# Actually save the attachments into their dated folders.
reconcile fetch --from 2026-03-02 --to 2026-03-06 --write

# Has everything arrived yet?
reconcile inventory --from 2026-03-02 --to 2026-03-06

# Cross-check one folder and write the report into it.
reconcile check "~/Statements/EXAMPLE_SOURCE/EXAMPLE_SOURCE 2026.03.02"
```

`fetch` is a dry run unless you pass `--write`. Copying files out of a mailbox onto disk should
be a deliberate choice, not something that happens because you mistyped a date.

`check` exits 0 when everything reconciles and 1 when it does not, so it slots into a script.

There is also `reconcile folders --week 2026-03-02`, which creates the week's empty folders in
advance (weekdays only -- statements do not arrive on Saturdays, and weekend folders would show
up as permanently missing in the inventory).

## The report

`check` writes `reconciliation_report.xlsx` into the folder, with four sheets:

| Sheet | What it holds |
|---|---|
| **Summary** | Counts per side, totals, and the verdict |
| **Differences** | Records found on both sides that disagree — field, both values, where to look (`match_on` mode only) |
| **Unmatched** | Every one-sided record, saying which side has it and which is missing it |
| **Unread Lines** | Document lines the reader could not interpret |
| **Matched** | Every matched pair, with where each came from |

The verdict is **FULLY RECONCILED** only when nothing is one-sided, nothing disagrees, the counts
agree, *and* nothing was left unread. That last condition matters: a line the reader could not
interpret is not evidence of agreement, it is a record nobody checked. Calling that "reconciled"
would be the one failure mode that hides a genuine break. An ambiguous identifier blocks it for
the same reason.

## How the comparison works

First the tool decides which document record and which spreadsheet record are the *same record*.
There are two ways, and which one you get depends on your documents.

### By identifier -- `match_on` (preferred)

Most transactional documents carry a reference that appears on both sides: an invoice number, a
transaction id. Point `match_on` at that field and records pair on it, after which **every other
field is compared**. A wrong value is then reported as exactly what it is:

> `INV-4471` — amount is `1,234.50` in the document and `1,243.50` in the spreadsheet

That lands on a **Differences** sheet, one row per disagreeing field, with the page and row to
look at. Use this mode whenever an identifier exists.

### By composite key -- `match_key` (fallback)

Some documents carry no identifier at all. Then a record can only be recognised by a combination
of its own values -- typically date + description + amount + quantity.

The trade-off is real and worth understanding before choosing this mode: a record whose amount
differs between the two files shows up as *two one-sided records*, not one difference. With
nothing tying the two rows together, there is no way to know they were meant to be the same
record, and claiming otherwise would be a guess that hides which side is wrong. If your documents
do have an identifier, `match_on` avoids this entirely.

### In both modes

Values are normalised before comparing, so `1,234.50`, `1.234,50` and the float `1234.5` all
count as the same number, and `02-Mar-2026` matches `2026-03-02`. Formatting is never reported as
a difference; the report still shows you the original values, since that is what you will be
looking at in the two files.

Pairing is one-for-one on repeats. If the same record genuinely occurs twice on both sides, both
pair up; a third occurrence on one side alone is reported. In `match_on` mode an identifier that
appears more than once on either side is flagged as **ambiguous** rather than paired silently --
the pairing behind it would be a guess about which copy goes with which.

On the PDF side the tool reads word positions, never a flat text dump. A text dump collapses
empty columns, so a row with no quantity silently shifts its amount one field left and the
reconciliation then confirms a number that was never on the page.

## Privacy

- Everything runs on your machine; nothing is sent anywhere.
- Outlook access uses the desktop app you are already signed into -- no password, no app
  registration, no token stored on disk.
- `.gitignore` blocks `*.pdf`, `*.xlsx`, `*.csv` and `config.yaml`, so real documents and your
  real mail-folder names cannot be committed by accident.
- Every test fixture in this repo is synthetic and generated at run time.

## Development

```bash
pytest -q --cov=src --cov-report=term-missing
ruff check . && black --check .
```

The Outlook layer sits behind small protocols and is tested with fakes, so the whole suite runs
anywhere -- no mailbox and no Windows required.

## Layout

```
src/statement_reconciler/
  config.py          load and validate the YAML; every domain fact lives here
  normalize.py       date / number / text canonicalisation
  records.py         the one record type both readers produce
  matching.py        composite-key matching and the verdict
  check.py           one folder end to end
  report.py          the Excel workbook
  inventory.py       which folders are incomplete
  cli.py             fetch | folders | check | inventory | probe
  documents/pdf.py       read a PDF by word position
  documents/tabular.py   read xlsx / xlsm / ods / csv / tsv
  mail/outlook.py        COM fetch, behind injectable protocols
  mail/naming.py         folder and filename rules, shared by fetch and inventory
```

## License

MIT.
