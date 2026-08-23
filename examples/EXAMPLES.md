# Who uses this, and what it catches

The job is always the same shape: **two records of the same events exist, and they need to
agree.** Usually one is a PDF from outside and the other is your own export — but neither side
has to be yours, and holding two outside parties to each other works exactly the same way.

Below are six settings where that turns up, what goes wrong in each, and the config that handles
it.

If you just want to see the output, skip to [Try it in 30 seconds](#try-it-in-30-seconds) — it
needs no documents of your own.

---

## The six examples

### Banking / treasury — `banking.yaml`

**Who.** Anyone doing daily cash reconciliation: a treasury analyst, a finance manager, a
bookkeeper closing the day.

**What arrives.** The bank emails a statement PDF each morning. Your accounting system exports
the day's cash movements to CSV.

**What goes wrong.** A payment leaves the bank but never posts to the ledger. A transfer is
booked twice. An amount is keyed with transposed digits and the day is out by an amount nobody
can find.

**Why `match_on: reference`.** Bank statements carry a transaction id, and so does your export.
Pairing on it means a wrong amount is reported as *that transaction's* amount being wrong,
rather than as two unexplained lines.

### Accounting firm — `accounting_firm.yaml`

**Who.** A practice checking supplier statements against purchase ledgers, for their own books
or a client's.

**What arrives.** Monthly statements from suppliers. Your purchase ledger export.

**What goes wrong.** The classic pair: the supplier billed something you never booked, and you
booked something they never billed. Both are invisible on a totals-only comparison, because they
can offset each other almost exactly.

**Why `match_on: reference`.** Invoice numbers are on both sides, so each of those two cases is
named individually instead of netting off.

### E-commerce / payments — `ecommerce.yaml`

**Who.** An online seller or a finance person reconciling a payment processor's settlement
against orders.

**What arrives.** A settlement statement from the processor. An order export from your platform.

**What goes wrong.** A refund is settled but never recorded. Fees change the net so the gross
never matches. An order settles in the next period and looks missing.

**Why `match_on: reference`.** Processors put a settlement or transaction id on every line.

### Payroll — `payroll.yaml`

**Who.** Payroll administrators checking a provider's remittance against what was approved.

**What arrives.** A remittance or funding statement. Your approved payroll register.

**What goes wrong.** A leaver is paid one cycle too long. A rate change applies to the wrong
period.

**Why `match_key`, not `match_on`.** Payroll lines frequently carry no shared reference — the
provider's internal id means nothing in your register. So records are identified by date +
description + amount together. Read the trade-off in the main README under
[How the comparison works](../README.md#how-the-comparison-works): without an id, a changed
amount appears as two one-sided rows rather than one difference, because nothing ties the two
rows together. **This is the fallback. If your documents do share an id, use `match_on`.**

### Insurance — `insurance.yaml`

**Who.** Brokers and agencies checking commission statements from insurers.

**What arrives.** A commission or premium statement. Your policy or commission register.

**What goes wrong.** Commission paid at the wrong rate. A policy that lapsed still being paid on.
A renewal missing from the statement entirely.

**Why `match_on: reference`.** Policy numbers appear on both sides.

### Two outside parties — `two_providers.yaml`

**Who.** Anyone sitting between two other organisations and answerable for the difference: a
landlord between a managing agent and a letting platform, a shipper between a freight forwarder
and a carrier, a fund operations team between an administrator and a custodian.

**What arrives.** A statement PDF from one party. A payout or manifest spreadsheet from the
other. Neither is yours.

**What goes wrong.** One party collects and the other never passes it on. A fee is deducted by
one and not recognised by the other. Something settles in a different period on each side, so
both parties' totals look right and the middle does not reconcile.

**What is different about it.** Nothing mechanical — one side is a PDF, the other tabular, and
they compare the same way. What changes is naming. "Spreadsheet" tells you nothing when it is
not yours, so this config sets `labels`:

```yaml
labels:
  document: "Managing agent statement"
  spreadsheet: "Platform payout file"
```

and every sheet in the report then names the parties instead of the file formats:

| Present in | Missing from | reference | description |
|---|---|---|---|
| Managing agent statement | Platform payout file | RC-8812 | Flat 4, March rent |

`labels` is optional and available to every source, not just this one. It changes only the
wording of the report -- the reconciliation is identical either way.

---

## Try it in 30 seconds

No documents of your own needed. This generates a supplier statement PDF, a ledger spreadsheet,
and a config wiring them together:

```bash
pip install -e ".[dev]"          # the demo draws a PDF, which needs reportlab
python examples/demo/build_demo.py
reconcile check --config demo/config.yaml "demo/ACME_SUPPLIES/ACME_SUPPLIES 2026.03.02"
```

The generated data contains one of each thing that can go wrong, so you get:

```
Document records:    4
Spreadsheet records: 4
Matched:             2
Differing:           1
One-sided:           2
Verdict:             DIFFERENCES FOUND
```

Open `reconciliation_report.xlsx` in that folder. The **Differences** sheet shows the transposed
amount, pinned to the record and the page:

| reference | Field | In document | In spreadsheet | Document at | Spreadsheet at |
|---|---|---|---|---|---|
| INV-4472 | amount | 899.00 | 989.00 | page 1, line 6 | row 3 |

and **Unmatched** shows the two that exist on one side only:

| Present in | Missing from | reference | description |
|---|---|---|---|
| Document | Spreadsheet | INV-4474 | Cable trays |
| Spreadsheet | Document | INV-4480 | Whiteboard markers |

That is the whole point of the tool in one screen: *the supplier billed you for cable trays you
never booked, you booked markers they never billed, and one invoice is out by 90.00.*

---

## Adapting one to your documents

1. **Copy the closest example.**

   ```bash
   cp examples/configs/banking.yaml config.yaml
   ```

2. **Set `output_root`** to where you want documents filed, and `mail_folders` to the Outlook
   folder your statements land in.

3. **Fix the column positions.** The x-positions in these files are placeholders — they will not
   match your layout. Run:

   ```bash
   reconcile probe your_statement.pdf --mask
   ```

   and read off where each column starts. `--mask` shows only the *shape* of each value
   (`9` for a digit, `A` for a capital), so you can paste the output into a chat or an issue
   without exposing anything real.

4. **Fix the column names.** Under `records`, list what your spreadsheet actually calls each
   field. If none of the names match, the error tells you what it tried and what your file has —
   so it is always a config edit, never a code change.

5. **Check one folder you already know the answer for**, before trusting it on a folder you
   don't:

   ```bash
   reconcile check "~/Statements/BANK_X/BANK_X 2026.03.02"
   ```

Then, once it is set up, the daily command is the range one:

```bash
reconcile check --from 2026-03-02 --to 2026-03-06
```

## Notes

- Column x-positions in every example are placeholders. Always run `reconcile probe` on a real
  document.
- `fetch` needs Windows with the classic Outlook desktop app. `check`, `probe` and `inventory`
  work on any platform, on files you already have — so you can try the tool before deciding
  whether to automate the download.
