# INPUT-SPEC — remittance-stub-parsing (client mode)

What to hand the parser in a client engagement. Derived from the code that
consumes the data (`src/extraction/plugins.py`, `pdf_extractor.py`,
`src/ledger/reconciliation.py`), not the README.

## 1. Remittance PDFs

A directory of the client's remittance-advice PDFs. Each is detected to a
**format plugin** by a header substring and parsed into a deduction ledger
(invoice number, reason code, description, amount) plus header/footer totals.

```bash
python client_mode.py --config engagement.yml --input client-data/stubs/ --out client-output
```

- One PDF per remittance. Multi-page PDFs are handled.
- A PDF that matches no known format plugin produces a **Data Readiness Report**
  naming it — never a silent skip.

## 2. Format plugins (adding a client's format is a config drop-in)

A remittance **format** is defined entirely by two YAML files under the client's
config directory — no code change, no enum edit:

- `format_configs/<name>.yml`
  ```yaml
  retailer: acme_grocery
  display_name: "Acme Grocery"
  header_pattern: "ACME GROCERY CO."      # page-1 substring that identifies the format
  column_mapping: {invoice_number: 0, reason_code: 1, description: 2, amount: 3}
  amount_format: "plain"                    # "plain" ($1,234.56) or "parenthesized" (($1,234.56))
  # header_labels: ["Invoice #", "Code", ...]   # optional; defaults to the shared set
  ```
- `reason_codes/<name>.yml`
  ```yaml
  codes:
    AG-01: {category: compliance, description: "Label noncompliance"}
  ```
  Categories: `promotional`, `logistics`, `compliance`, `financial`, `operational`, `unknown`.

Point `engagement.yml` at the directory holding these:
```yaml
format_config_dir: "client-data/config"   # defaults to the built-in src/config
```
The four built-in formats (Walmart, Costco, UNFI, KeHE) ship as plugins; a client
who uses them needs no config.

## 3. Reference AR ledger

The client's accounts-receivable ledger, used to reconcile which deductions can
be verified and to compute dispute-window exposure. JSON or CSV/XLSX:

- JSON: `{"invoices": {"<invoice_number>": {"amount": "2450.00", "date": "2025-03-15"}}}`
- CSV/XLSX columns: `invoice_number`, `amount`, `date` (ISO).

```yaml
reference_ledger: "client-data/ar_ledger.csv"
```

Without a ledger the run proceeds with a **warning** and omits recoverable totals.

## 4. Basis & window (engagement.yml)

```yaml
as_of_date: "2026-07-30"          # reconciliation anchor; NEVER today's date
basis:
  dispute_window_days: 90         # dispute window length; printed on the output
  window_label: "90-day dispute window"
```

Dispute-window exposure is measured **as of `as_of_date`**, from config — never the
wall clock (the live-clock lesson).

## Output

To `client-output/` (gitignored): a branded, provenance-footed (each input PDF's
SHA-256, `as_of_date`, config hash), DRAFT-watermarked
`remittance-recovery-summary.html` (recoverable total split within/past window, by
format, by category) + `json/summary.json`; or a `data-readiness-report.html` if a
PDF doesn't detect or the ledger is missing.
