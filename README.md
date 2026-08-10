# Remittance Stub Parsing

Turns retailer and distributor remittance-advice PDFs into a unified, classified, reconciled deduction ledger — and flags what needs human review before the dispute window closes.

**Live:** https://remittance.lailarallc.com

## What it does

Multi-format parser covering Walmart, Costco, UNFI, and KeHE — the four formats that account for the majority of specialty food trade spend:

- **Hybrid extraction pipeline:** pdfplumber (deterministic, free) runs first; Claude API (structured output via forced tool_choice) runs second when an API key is available. The pipeline picks whichever found more deductions.
- **Deterministic validation:** net cash + sum(deductions) must equal gross invoice. If it doesn't balance, the stub routes to a human review queue — no model confidence scores involved.
- **Reason-code classification** against per-retailer YAML configs. Unmapped codes get flagged.
- **SQLite ledger** with Decimal-as-text for penny-exact monetary storage.
- **Reconciliation against the Cinderhaven SSOT:** 3,357 chargebacks (2,873 retailer + 484 distributor), ~$3.6M/yr all-in trade cost, 36-month window.
- **Interactive demo** with guided tour (SSE streaming), free exploration, and a review queue with side-by-side PDF viewer + editable form.
- **Dynamic case study** (HTML + PDF via WeasyPrint) with Cinderhaven findings.

## Why it matters

Every retailer remittance arrives with deductions baked in — chargebacks, allowances, fines — each described in a different PDF format with a different reason-code vocabulary. Most brands key these by hand into a spreadsheet, late or never. The consequence is direct: deductions that aren't identified and classified before the retailer's dispute deadline become unrecoverable, regardless of merit.

A unified ledger with arithmetic validation changes the economics. Extraction is automated, mismatches surface immediately instead of at month-end, and the review queue concentrates scarce human attention on exactly the stubs that don't balance — while the dispute window is still open.

## Quick start

```bash
git clone https://github.com/MsShawnP/remittance-stub-parsing.git
cd remittance-stub-parsing
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
pip install -e .

# Generate synthetic test stubs
python -c "from src.stub_generator import generate_all_stubs; from pathlib import Path; generate_all_stubs(Path('stubs'))"

# Run the app
uvicorn app.main:app --reload

# Run tests
pytest
```

The app works without an `ANTHROPIC_API_KEY` — pdfplumber handles extraction alone. Set the key to enable the hybrid LLM pipeline for better results on variable line-item tables.

## Tech stack

- Python 3.12+
- pdfplumber — PDF table extraction from native-text PDFs
- anthropic — Claude Haiku 4.5 for structured LLM extraction
- Pydantic — data models and validation
- FastAPI + Uvicorn — web server
- Jinja2 + HTMX + SSE (sse-starlette) — templates and interactivity, no build step
- aiosqlite — async SQLite access
- WeasyPrint — CSS Paged Media PDF report generation
- FPDF2 — synthetic test stub generation
- PyYAML — per-retailer reason-code configs
- Fly.io — deployment (Docker, pango/cairo for WeasyPrint)

## Project structure

- `src/` — extraction, validation, ledger, models, stub generator, per-retailer configs
- `app/` — FastAPI routes, templates, static assets
- `stubs/` — generated synthetic remittance PDFs
- `tests/` — pytest suite
- `screenshots/` — landing page, guided tour, explorer, review queue

## Data contract

**Canonical baseline:** 50 SKUs · 5 product lines (AS·PS·SC·DG·SB) · 6 retailers (Walmart·Costco·Whole Foods·Sprouts·Kroger·Regional Group) · 10 channels (6 retail + UNFI·KeHE·DPI + DTC). Cinderhaven is a fictional ~$25M specialty food brand; data is synthetic, methodology and deliverables are real. Reconciliation uses the canonical 3,357 chargebacks and ~$3.6M/yr all-in trade cost from cinderhaven-data-platform.

## Client engagement use

The demo parses the committed Cinderhaven stubs. To parse a **client's own
remittance PDFs** in place — validated, never committed, never deployed — use
client mode (see [INPUT-SPEC.md](INPUT-SPEC.md)):

```bash
pip install -e ../engagement-template/lib      # the shared lailara_engagement scaffold
python client_mode.py --config engagement.yml --input client-data/stubs/ --out client-output [--final]
```

Every PDF is detected to a **format plugin** and parsed; a client's own remittance
format is a config drop-in (`format_configs/<name>.yml` + `reason_codes/<name>.yml`
in the client config dir — no code change, no enum edit). Deductions are reconciled
against the client's AR ledger as of the config `as_of_date` (never the wall clock).
A PDF that matches no format, or a missing ledger, yields a branded **Data Readiness
Report**. On success, `client-output/` (gitignored) gets a branded, provenance-footed
(each PDF's SHA-256), DRAFT-watermarked recoverable-deductions summary + `summary.json`.
Client identity, window, ledger, and format dir come from `engagement.yml` (copy
[`engagement.demo.yml`](engagement.demo.yml)).

## License

MIT — see [LICENSE](LICENSE).

---

Built by [Lailara LLC](https://lailarallc.com) — data hygiene and analytics consulting for specialty food brands scaling into national retail.
