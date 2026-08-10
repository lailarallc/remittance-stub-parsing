# Remittance Stub Parsing — Decisions Log

Permanent record of choices that should survive session turnover.
If a decision is reversed, strike it through and add the replacement
below — don't delete.

---

## Format

Each entry:
- **Date** — when decided
- **Decision** — one sentence, imperative voice
- **Why** — the reasoning, including what was tried and rejected
- **Scope** — what this applies to (file, chunk, deliverable, or "global")
- **Do not** — explicit anti-instructions, if any

---

## Architecture & Pipeline

### 2026-06-08 — Use pure ASGI middleware for response headers, not BaseHTTPMiddleware
- **Why:** Starlette 1.0.1's `BaseHTTPMiddleware` silently drops headers set via `response.headers[...]` when running through uvicorn (works in TestClient but not in production). A pure ASGI middleware that intercepts `http.response.start` messages and appends header bytes directly is reliable across all transports.
- **Scope:** app/main.py — CSPMiddleware class and any future response-header middleware
- **Do not:** Use `BaseHTTPMiddleware` for setting response headers. If adding new middleware that modifies headers, follow the pure ASGI pattern in CSPMiddleware.

---

### 2026-06-04 — Use deterministic validation (arithmetic check) as the trust signal, not model confidence
- **Why:** Raw LLM/OCR token confidence is unreliable on financial documents — a wrong number can return at 99% confidence. The pipeline enforces `net cash + sum(deductions) = gross invoice` and reason-code mapping. If it balances and maps, verified; if not, routes to human review.
- **Scope:** Global — applies to all extraction paths
- **Do not:** Show or rely on model confidence percentages as quality indicators

---

### 2026-06-04 — Drop the OCR/scanned-image pipeline; all four synthetic formats are native-text PDFs
- **Why:** Building a robust OCR pipeline for scanned financial documents is a different problem from native-text extraction. Since we control the synthetic stubs, OCR adds engineering cost without portfolio value. The architecture can note OCR support for production use.
- **Scope:** Global — all four stub formats
- **Do not:** Build or integrate PaddleOCR/Marker/Tesseract for this build arc

### 2026-06-04 — Demo parses only the four known synthetic formats, not arbitrary uploads
- **Why:** Handling unknown formats on first contact is a significantly harder problem. The demo proves the pipeline on realistic formats; it does not claim to be a general-purpose parser.
- **Scope:** Demo surface
- **Do not:** Accept or attempt to parse user-uploaded PDFs of unknown layout

### 2026-06-04 — Include intentionally broken stubs to exercise the review queue
- **Why:** Clean data is the fantasy. The review queue is a working feature, not a placeholder. Broken stubs (mismatched amounts, unmapped reason codes) demonstrate the real failure modes and the human-in-the-loop escalation path.
- **Scope:** Synthetic stub generation

### 2026-06-04 — Demo is an educational walkthrough, not just a technical tool
- **Why:** The audience may not know what's required to reconcile messy remittance data. The demo teaches the full process (parsing → validation → reconciliation) while proving the practice can do it.
- **Scope:** Demo surface, case study

### 2026-06-04 — Tech stack is genuinely open; best tools to make this shine
- **Why:** User wants the strongest possible portfolio piece. No sacred cows from the brief — Python is the language, everything else decided during /ce:plan based on research.
- **Scope:** Global

---

### 2026-06-04 — Use pdfplumber for PDF table extraction
- **Why:** MIT licensed, best table detection from layout geometry for financial PDFs with inconsistent headers. Visual debugging (`debug_tablefinder()`) invaluable during development. PyMuPDF is faster but AGPL-licensed (source disclosure for web apps) and weaker at table grouping. camelot-py struggles with borderless tables common in remittance stubs.
- **Scope:** Extraction engine (src/extraction/pdf_extractor.py)
- **Do not:** Use PyMuPDF (AGPL license incompatible with web app deployment)

### 2026-06-04 — Use Claude API with Pydantic structured outputs for LLM extraction
- **Why:** Schema-guaranteed output via constrained decoding — model cannot produce tokens violating the Pydantic schema. `messages.parse()` returns typed Python objects. Haiku 4.5 is cost-effective (~$2 for 500 stubs). Hybrid pipeline: pdfplumber first (deterministic, free), Claude API second for variable line-item tables.
- **Scope:** Extraction engine (src/extraction/llm_extractor.py)

### 2026-06-04 — Use FastAPI + HTMX + Jinja2 for demo surface
- **Why:** Native SSE for streaming pipeline progress. Pydantic models shared across extraction and API layers. No build step — ~5KB JS total. Side-by-side PDF viewer + editable form is snappy in HTMX where Streamlit is clunky.
- **Scope:** Demo surface (app/)

### 2026-06-04 — Use WeasyPrint for dynamic PDF reports
- **Why:** CSS Paged Media for professional print layout (page breaks, running headers/footers, page counters). SVG rendered as vectors — matches Lailara design system requirement. Jinja2 templates shared with web layer. Requires Debian-based Docker (not Alpine).
- **Scope:** Case study generation (app/routes/report.py)

### 2026-06-04 — Use FPDF2 for synthetic stub generation
- **Why:** Pure Python, zero system deps. Canvas-based API gives pixel-level control over PDF internals the parser will encounter. Intentional error injection is straightforward. ReportLab is more powerful but unnecessarily complex for fixed-layout test data.
- **Scope:** Synthetic stubs (src/stub_generator/)

### 2026-06-04 — Deploy on Fly.io (not Cloudflare Workers)
- **Why:** WeasyPrint requires pango/cairo system libraries unavailable in Cloudflare Workers/Pages. Fly.io supports custom Dockerfiles, persistent volumes for SQLite, and custom domains. `fly scale count 1` ensures single-writer SQLite integrity.
- **Scope:** Deployment (Dockerfile, fly.toml)
- **Do not:** Use Cloudflare Workers for this project

### 2026-06-04 — Reason-code mapping as YAML config per retailer
- **Why:** Follows config-as-artifact pattern from other Lailara projects (Dimension & Weight's cost_params.yml, Item Setup Form's partner schemas). Per-retailer YAML files readable by practitioners, serve as a deliverable.
- **Scope:** Config (src/config/reason_codes/)

---

## Data & Schema

### 2026-06-04 — Canonical Cinderhaven figures locked from current Postgres SSOT (option a)

- **Why:** Legacy figures ($5.4M / 464 chargebacks / 18 months) were wrong on all three counts. 464 was a misquoted per-channel deduction count from the deduction-recovery project (DPI Northwest's deductions), not total chargebacks. $5.4M was from a pre-May-2026 data seed, superseded by a May 2026 regen ($7.2M), then superseded again by the current Postgres regen ($3.4M annualized). "18 months" was always 36 months. Verified by querying cinderhaven-db Postgres directly on 2026-06-04.
- **Scope:** Global — all references to Cinderhaven trade cost, chargeback count, and time window
- **Canonical values:**
  - All-in trade cost: $3.4M annualized / $10.3M over 36 months (structural trade + operational waste excl promo_billback)
  - Rate: ~10.8% of trailing-52w scan revenue ($32.5M)
  - Chargebacks: 864 (690 retailer + 174 distributor, gross = net, no reversals)
  - Window: 2024-01-01 to 2027-01-02 (36 months)
  - EBITDA check: plausible (13.7% trade + 11% EBITDA = 24.7%, leaves 75.3% for COGS+SGA)
- **Do not:** Use $5.4M, $7.2M, 464, or "18 months" anywhere. All are dead.

### 2026-06-04 — All-in trade cost definition: structural + operational waste (excl promo_billback)

- **Why:** Matches the trade-spend-data-diagnostic methodology exactly. Structural = AVG(trade_spend_pct) × trailing-52w scan revenue per channel. Operational waste = trailing-365 deductions excluding promo_billback (already captured in structural rates — including it would double-count). Chargebacks (separate table) overlap with deduction types and are NOT added to all-in.
- **Scope:** Global — any computation or citation of "all-in trade cost"
- **Do not:** Add chargebacks on top of all-in. Do not include promo_billback in operational waste.

### ~~2026-06-04 — Trade-spend-data-diagnostic SQLite export is stale; needs re-lock in a separate session~~

~~- **Why:** The Postgres data was intentionally regenerated after the May 2026 SQLite export. Trade_spend_pct values dropped ~50% (e.g. Walmart 21.5% → 12.0%), chargebacks went from 3,441 → 864, deductions from 7,837 → 15,898. The diagnostic's locked $7,174,939 / 26.1% no longer matches the SSOT.~~
~~- **Scope:** trade-spend-data-diagnostic project (separate repo)~~
~~- **Do not:** Cite the diagnostic's old numbers ($7.17M, 26.1%) as current~~

**Superseded 2026-06-05:** SQLite re-exported from Postgres v2. Workbook rebuilt and validated (59/59). Narrative docs still pending rewrite.

### 2026-06-05 — Dimension-weight illustrative calc (121) kept as-is with uncalibrated note

- **Why:** The `14% × 864 = 121` calc in build_spec_dimension_integrity.md is a recomputation from an illustrative `# PARAM` placeholder. Decision: keep the derived result but add inline note marking 14% attribution and $250/event as UNCALIBRATED placeholders to calibrate at build. Base 864 is canonical; derived 121 is not.
- **Scope:** dimension-weight-integrity build spec, lines 91–92
- **Do not:** Treat 121 or $30,250 as canonical figures. They are illustrative only.

### 2026-06-05 — check_canonical.py reads expected values from CINDERHAVEN_CANONICAL.md, not hardcoded

- **Why:** Expected figures are parsed from the canonical markdown file at runtime. This ensures the guard breaks if canonical.md is edited without a corresponding Postgres change (or vice versa), rather than silently passing against stale hardcoded values.
- **Scope:** cinderhaven-data-platform freeze guard
- **Do not:** Hardcode expected values in the guard script

### 2026-06-05 — Scenario-branch pattern: baseline (default) vs distressed (trade-spend-diagnostic only)

- **Why:** The v2 canonical data ($480K/yr waste, 44% recovery, 0 vague, 0 double-dips) is correct for all 11+ portfolio pieces but makes the trade-spend-diagnostic's exposé narrative impossible — the story depends on finding messy operational waste. Rather than re-baselining v2 (which would break every other piece), a named scenario generates an alternate deduction layer consumed only by the diagnostic. Baseline stays untouched as the default.
- **Scope:** cinderhaven-data-platform (SCENARIO flag, generate_distressed_scenario.py); trade-spend-diagnostic (consumer)
- **Do not:** Change baseline data. Do not let any piece other than trade-spend-diagnostic read the distressed dataset.

### 2026-06-05 — Distressed scenario uses isolated RNG (SEED=200) to avoid cascade to baseline

- **Why:** seed_retailer.py uses a single RNG stream (seed=100) for orders → shipments → deductions → disputes → chargebacks. Modifying deduction parameters mid-stream would shift every subsequent RNG call, cascading to chargeback counts and dispute outcomes. The distressed generator uses a completely separate RNG (seed=200) operating on a COPY of the baseline SQLite, so baseline tables are byte-identical.
- **Scope:** generate_distressed_scenario.py
- **Do not:** Share RNG state between baseline and distressed generation

---

### 2026-06-08 — Claude LLM extraction uses forced tool_choice, not JSON mode

- **Why:** `tool_choice: {type: "tool", name: "record_deductions"}` forces the model to call the tool with the exact schema. This guarantees structured output matching the Pydantic model without post-hoc parsing or retry loops. JSON mode alone can produce valid JSON that doesn't match the expected schema.
- **Scope:** src/extraction/llm_extractor.py
- **Do not:** Use JSON mode or unstructured text extraction for the LLM path

### 2026-06-08 — SQLite stores Decimal amounts as TEXT strings, not REAL

- **Why:** IEEE 754 floats cannot represent $42.50 exactly. Storing as TEXT preserves the exact decimal representation through round-trips. The validation layer compares penny-exact totals — floating-point drift would cause false validation failures.
- **Scope:** src/ledger/database.py, all amount columns
- **Do not:** Use REAL or FLOAT column types for monetary amounts

### 2026-06-08 — Hybrid extraction pipeline: pdfplumber first, LLM second, winner by deduction count

- **Why:** pdfplumber is deterministic, free, and fast. LLM extraction costs money and adds latency. The pipeline runs pdfplumber first; if an API key is available, it also runs the LLM path and picks whichever found more deductions. This means the demo works without an API key (graceful degradation) while getting better results when one is available.
- **Scope:** src/extraction/pipeline.py
- **Do not:** Require an API key for the demo to function

### 2026-06-08 — Separate Jinja2 templates for web case study (extends base) and PDF (standalone)

- **Why:** Jinja2 does not allow `{% extends %}` inside `{% if %}` blocks — extends must be the first tag. The web version needs the base layout (nav, CSS, scripts); the WeasyPrint PDF version needs a self-contained HTML document with embedded CSS for print. Two templates sharing the same section partials (hook, proof, evidence, margin_math).
- **Scope:** app/templates/report/case_study.html, case_study_pdf.html
- **Do not:** Try to combine into a single template with conditional extends

### 2026-06-08 — All user-supplied filenames must pass path traversal validation before filesystem access

- **Why:** 12-reviewer code review found P0 path traversal across 7 endpoints. `STUBS_DIR / user_input` allows directory escape via `../../`. Added `_safe_stub_path()` using `resolve().is_relative_to()` in every route module. Also added 10MB file-size cap in demo routes.
- **Scope:** All file-serving endpoints in app/routes/ (demo, tour, review, report)
- **Do not:** Construct paths from user input without `resolve().is_relative_to()` validation

### 2026-06-08 — All synchronous extraction calls in async handlers must use asyncio.to_thread

- **Why:** pdfplumber reads are synchronous and block the event loop when called from `async def` handlers. Under concurrent requests the server becomes unresponsive. All `extract()` and `extract_stub()` calls wrapped with `asyncio.to_thread()`.
- **Scope:** All async route handlers that call extraction functions
- **Do not:** Call `extract()`, `extract_stub()`, or `_process_stubs()` directly from async handlers

### 2026-06-08 — payment_date is Optional on RemittanceStub (not required)

- **Why:** Header extraction returns None when payment date regex doesn't match. Making the field required would crash on malformed PDFs. Downstream code (reconciliation) already handles None gracefully via `if deduction_date:` guard.
- **Scope:** src/models.py, all consumers of RemittanceStub.payment_date
- **Do not:** Assume payment_date is always present — check for None before date arithmetic

### 2026-06-08 — Self-host all third-party JavaScript; no CDN script loading

- **Why:** htmx and htmx-ext-sse were loaded from unpkg.com CDN without integrity hashes. A CDN compromise could inject JS into pages displaying financial data. Self-hosting matches the existing pattern for fonts (Playfair Display + Source Sans 3 already self-hosted for this reason). Content-Security-Policy middleware now blocks all external script/style/font sources.
- **Scope:** app/templates/base.html, app/static/js/, app/main.py (CSP middleware)
- **Do not:** Load JavaScript from external CDNs. Vendor scripts into static/js/ at pinned versions.

### 2026-06-08 — Never expose raw exception messages to clients

- **Why:** WeasyPrint and pdfplumber exceptions include absolute filesystem paths, library versions, and internal stack details. Sending `str(e)` to the client leaks server layout information. Log the real exception server-side; return a generic message to the client.
- **Scope:** All route error handlers, especially report.py PDF generation
- **Do not:** Include `str(e)` or `repr(e)` in HTTP response bodies

### 2026-06-25 — No traffic-light color signaling anywhere in the tool

- **Why:** The Lailara design system does not use color to signal good/bad, pass/fail, or safe/danger. Teal backgrounds for "verified/recovery/pass" and pink/red backgrounds for "flagged/forfeit/fail" read as green-means-good / red-means-bad regardless of the actual hex codes. The word on the badge or the label text communicates the status, not the color. Removed 6 CSS variables (--pass-bg, --pass-text, --fail-bg, --fail-text, --warn-bg, --warn-text) and unified all stat cards, badges, callout boxes, check indicators, field states, and progress dots to navy/ink/white.
- **Scope:** Global — main.css, case_study_pdf.html, all templates that use status badges, stat cards, callout boxes, check marks, or field states
- **Do not:** Reintroduce colored backgrounds or text that signal good/bad. No green family for "pass," no red family for "fail," no amber for "warning." All badges use navy bg + white text. All stat cards use white bg + navy left border + ink text. All callout boxes use white bg + navy left border + ink text.

### 2026-06-25 — Text containers use 800px max-width; data elements remain unconstrained within 1200px content container

- **Why:** 660px text alongside 1200px-wide data elements (stat cards, tables, charts) created a jarring visual mismatch — the page looked like two layouts stitched together. Tried 1200px text first but that made paragraphs unreadable (~120 chars/line). 800px (~80-85 chars/line) is within the readable range while closing the gap. The `.report-selector` form uses the same 800px. The SVG chart container matches at 800px. Data elements (stat rows, tables, callout boxes) inherit from the 1200px content container with no cap.
- **Scope:** main.css — `.hero-body`, `.tour-intro`, `.tour-step-desc`, `.tour-summary-text`, `.explore-intro`, `.review-intro`, `.report-subtitle`, `.report-body`, `.report-selector`, `.report-svg-chart`
- **Do not:** Set text body elements to `var(--content-max-width)` (1200px) or remove their max-width entirely. Do not constrain data elements (stat cards, tables, grids) to the text width.

### 2026-06-25 — Review detail layout uses 40/60 split (PDF viewer / form panel)

- **Why:** Original `3fr 2fr` (60/40) gave the PDF viewer 60% and the form panel 40%. At 40%, reason code descriptions like "Advertising allowance" and "Freight allowance" truncated in the editable deductions table. The PDF viewer doesn't need more than 40% — the PDF content is fixed-width and the browser viewer scales to fit. The form panel needs the extra room for its 4-column table (Invoice #, Reason Code, Description, Amount).
- **Scope:** main.css — `.split-layout` grid-template-columns
- **Do not:** Give the PDF viewer more than 50% of the split. The form panel is the interactive element; the PDF is reference-only.

---

## Visualization

[Chart conventions, palette decisions, interactivity choices]

---

## Output Formats

[Decisions about deliverable formats, structure, organization]

---

## Writing & Voice

[Voice, style, terminology decisions specific to this project]

---

## Reversed / Superseded

When a decision is overturned:
1. Strike through the original entry above (don't delete)
2. Add a new entry below with the replacement decision
3. Note the link in both directions

This preserves the history of why something is the way it is.

---

## 2026-08-08 — reference_ledger DATA_DIR hardcode: reviewed, accepted

- **Decision** — Leave `app/routes/report.py` loading the reference ledger via the
  `DATA_DIR` constant path rather than `config.reference_ledger`.
- **Why** — Surfaced by the 0.d config-surface audit. Unlike `as_of_date` and
  `dispute_window_days` (each fed a rendered label while a module constant fed the math —
  a caption-vs-math divergence, now fixed), `reference_ledger` is a data-source path in
  the same repo. `DATA_DIR/"cinderhaven_reference.json"` and `config.reference_ledger`
  resolve to the same file; nothing can silently disagree with it, so it is not the same
  defect class. Fixing it would be churn without risk reduction.
- **Scope** — `app/routes/report.py` (demo web path). `client_mode.py` already reads
  `config.reference_ledger`. Reviewed-and-accepted (Shawn, 2026-08-08) so it is not
  re-litigated.
