# Example configs for common sectors

This directory contains example config YAMLs you can copy into `config.yaml` and tweak for your setup.

How to use

1. Pick one example file from `examples/configs/` and copy it to the repository root as `config.yaml` (or pass `--config` to the CLI):

```bash
cp examples/configs/banking.yaml config.yaml
# or
cp examples/configs/ecommerce.yaml config.yaml
```

2. Edit `config.yaml` to set `output_root` and adjust `document.columns` by running `reconcile probe <some-statement.pdf> --mask` and copying the x positions into the file.

3. Dry-run fetching (Windows + classic Outlook required for fetch):

```bash
reconcile fetch --from 2026-03-02 --to 2026-03-06
```

4. Save attachments:

```bash
reconcile fetch --from 2026-03-02 --to 2026-03-06 --write
```

5. Reconcile a folder and generate the Excel report:

```bash
reconcile check "~/Statements/BANK_X/BANK_X 2026.03.02"
```

Files included

- banking.yaml — Banking / Treasury example (match_on transaction reference)
- accounting_firm.yaml — Client/vendor supplier statements
- ecommerce.yaml — Payment processor / settlement statements
- payroll.yaml — Payroll and remittance statements (match_key example)
- insurance.yaml — Commission / premium statements

Notes

- Column x-positions in these examples are placeholders. Run `reconcile probe` on a real PDF to pick the correct x coordinates for your layout.
- `fetch` requires the Windows classic Outlook desktop app; `check` and `probe` work cross-platform on downloaded files.
