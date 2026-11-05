# Portfolio Project Brief: Remittance Stub Parsing

**Status:** Brainstorm / Brief stage
**Tier:** 2 (fixed-fee diagnostic + reusable extraction engine)
**Priority:** Next build after Dimension & Weight Integrity. Chosen on capability-gap grounds, not list order — it's the first published piece to demonstrate document AI / OCR → structured, the largest hole in the current tool story, and it closes a loop with the already-shipped Deduction Recovery piece.
**Backlog ref:** #58 (Remittance stub PDF parsing, scored 30/35)

---

### 1. The Pain

Every dollar a retailer or distributor pays Cinderhaven arrives with a **remittance advice** — a PDF (or a portal screen they print to PDF) listing what's being paid, what's being deducted, and a reason code for each deduction. The national mass retailer pays an invoice and nets out $4,200 across eleven line items. UNFI remits on a stub with promotional deduction codes that don't match anything in the ERP. KeHE sends a different format again. Costco, different still.

Nobody can act on a PDF. So today someone — usually an AP clerk or the controller — opens each stub, reads the line items, and **manually keys them into a spreadsheet** to figure out: what got paid, what got taken, why, and whether the deduction was legitimate. The data the entire Deduction Recovery analysis depends on is trapped in documents, extracted by hand, one stub at a time.

- **Who feels it most:** Controller / AP lead operationally; CFO strategically (they know money is leaking but can't see where without the manual pull).
- **When it gets acute:** The moment a brand adds a second and third distributor. One remittance format is annoying; four formats across hundreds of stubs a month is a part-time job nobody owns.
- **How it compounds:** Volume scales with retailers × SKUs × promo frequency. At $25M it's a few hours a week. At $50M the manual pull is so far behind that deductions age past the dispute window before anyone reconciles them — the leak becomes permanent because the *data arrived too late to fight*.

#### The Status Quo

A shared-drive folder of downloaded PDFs and a running Excel workbook where someone retypes line items. Reason codes get loosely categorized by hand ("I think this one's a shortage"). Disputes happen only for the big obvious ones; everything under a few hundred dollars is written off because reconciling it costs more than recovering it. The workbook is always weeks behind.

### 2. Why This Piece

The published portfolio proves the practice can analyze structured data — SQL tables, CSVs, scraped pages, dbt models. **It does not yet prove the practice can get data out of documents.** That's the single biggest capability gap, and it's where the brainstorm scores cluster highest (the 32–33 band is dominated by document-parsing ideas: item setup forms, spec sheets, BOLs, remittance stubs).

This piece fills that gap with the document type that compounds hardest:

- **Closes a loop with Deduction Recovery (shipped).** That piece showed what to *do* with deduction data. This shows how you *get* it out of the retailer's PDF in the first place. Together they're an end-to-end story: PDF in → reconciliation → recovery.
- **Feeds Trade Spend Leakage (shipped).** Net-revenue-by-retailer math is only as good as the deduction data behind it. This is the intake pipe.
- **New capability, not a rerun.** Backlog #1 (Interactive Data Debt Story) would re-demonstrate scroll-driven D3 already proven in "Where the Money Actually Comes From." This adds OCR / document AI / extraction-confidence handling — genuinely new to the tool list.
- **Reinforces the primary buyer**, no new persona needed. Same CFO/controller, same money-leak framing.

### 3. The Portfolio Piece

**Working title:** *The $40,000 Hiding in Your Remittance PDFs* (alt: *Your Deductions Arrive as PDFs. Your Recovery Window Doesn't Wait.*)

The reader meets a stack of remittance stubs — the thing piling up in their AP folder right now. They watch four different retailer formats get turned into one clean reconciliation table, with deductions classified by reason code and flagged against the dispute clock. The arc is: *this pile of PDFs is unactionable → here is the same pile as a queryable ledger → here is the money in it you're about to lose to the calendar.*

#### Structure

- **Part 1 — The hook:** A side-by-side of four real remittance formats (Walmart, UNFI, KeHE, Costco — realistic stand-ins). Same underlying event — a payment with deductions — rendered four incompatible ways. The visceral "this is why nobody reconciles these" moment.
- **Part 2 — The proof:** Cinderhaven case study. Run the parser across a quarter of stubs. Output: a unified deduction ledger, reason-code classification, a reconciliation against the AR/invoice records, and an **aging-vs-dispute-window** view showing dollars about to expire. The headline finding is a recoverable figure that ties back to the ~$380K/yr operational deduction waste (3,357 chargebacks over 36 months).
- **Part 3 — The evidence:** The extraction engine itself — hybrid parser (deterministic extraction for stable layout blocks + structured LLM extraction for variable line-item tables), OCR for scanned/image stubs, and a **deterministic validation loop** that proves each extraction before trusting it. The trust signal is *not* a model confidence percentage — raw LLM/OCR token confidence is unreliable on financial documents (a wrong number can come back at 99% confidence). Instead the pipeline enforces arithmetic: `net cash received + Σ line deductions = gross invoice amount`. If it balances to the penny and every reason code maps to a known category, the row is verified; if not, it routes to a human-review queue regardless of what the model claims. The credibility move is *not* claiming 100% automation — it's a pipeline that trusts the arithmetic over the model and knows exactly when to escalate.

#### The Margin Math

Anchor to Cinderhaven's existing numbers (3,357 chargebacks / 36 months, ~$3.6M/yr all-in trade spend, 11.0% of scan revenue). Frame three layers:

- **Recovery:** A realistic slice of deductions are invalid/disputable. If even a low-single-digit percent of trade cost is wrongly deducted and currently un-disputed because it's never reconciled in time, that's tens of thousands of dollars a year walking out — quantify against the ~$380K/yr operational deduction waste.
- **Labor:** Hours/month of manual keying eliminated, costed at a loaded controller/AP rate.
- **The window:** The deductions that age out of the dispute window unrecovered — money that is *100% lost* purely because the manual pull was too slow. This is the sharpest number: it's not inefficiency, it's forfeit.

#### Before / After

- **Before:** A folder of PDFs and an Excel workbook three weeks behind. Disputes filed only for the obvious big hits; everything small written off. CFO knows money leaks, can't see where.
- **After:** Stubs land → unified deduction ledger, classified and reconciled, with a flag list of "dispute these N items totaling $X before they expire." The CFO opens one view and knows exactly what to fight.

#### Who Else Sees This?

- **Primary audience:** CFO / controller.
- **Secondary audience:** AP clerk (who lives the manual pull and will champion it), and the broker (who actually files some disputes).
- **How it gets shared:** Controller forwards to the CFO with "this is the thing I've been keying by hand." CFO forwards to the broker with "why aren't we disputing these?"

### 4. Technical Specification

#### Repo

- **Repo name:** `remittance-parser`
- **Repo description:** Multi-format retailer/distributor remittance-advice parser → unified, classified, reconciled deduction ledger.

#### Architecture

```
        Multi-format PDF ingestion
                  │
        ┌─────────┴─────────┐
        ▼                   ▼
  Native text layer    Scanned/image layer
   (pdfplumber)          (PaddleOCR)
        └─────────┬─────────┘
                  ▼
   Structured extraction  (LLM → JSON / Pydantic)
   deterministic parse for stable blocks;
   LLM extraction for variable line-item tables
                  │
                  ▼
   Deterministic validation
   net cash + Σ deductions == gross invoice?
   every reason code maps to a known category?
        ┌─────────┴─────────┐
        ▼                   ▼
  Balances + maps      Fails / unmapped
  → auto-verified      → HTMX review queue
        └─────────┬─────────┘
                  ▼
        Unified SQLite ledger
   (reconciled against ERP invoice/AR records)
```

#### Tech Stack

| Tool | Role in This Project |
|------|---------------------|
| Python | Orchestration, parsing logic, reconciliation |
| pdfplumber | Deterministic native-PDF text + table extraction for stable layout blocks |
| PaddleOCR (or Marker) | Layout-aware OCR for scanned/image-only stubs — *not* raw Tesseract, which produces gibberish on multi-column financial tables |
| LLM extraction (JSON / Pydantic) | Structured extraction of the variable line-item tables that defeat a fixed parser; outputs typed records (item, amount, reason code) |
| Deterministic validation layer | Balancing math (`net + Σ deductions = gross`) + reason-code mapping check; the actual trust signal, replacing model confidence |
| pandas | Ledger assembly, reconciliation, aging math |
| SQLite | Output ledger as a queryable table; reconcile against invoice/AR records |
| FastAPI + HTMX | Demo surface + human-in-the-loop review queue (side-by-side PDF viewer + editable form, snappy in HTMX where Streamlit is clunky) |

#### Deliverables

| Deliverable | Format | Purpose |
|------------|--------|---------|
| Extraction engine | Python package in repo | Technical credibility — practitioners can read the parser + the deterministic validation logic |
| Unified deduction ledger | SQLite table / CSV + sample queries | Shows the "PDF → queryable" payoff |
| Case study write-up | HTML + PDF | The narrative proof, Cinderhaven findings |
| Interactive demo + review queue | FastAPI + HTMX web app (drop a stub, see it parsed, verify flagged rows) | Lead gen — ops people try their own format |
| Synthetic remittance stubs | PDF set (4 formats: Walmart, Costco, UNFI, KeHE — one distributor stub rendered as a scanned image to exercise the OCR path) | Reusable Cinderhaven asset; safe to publish |

#### Deployment

- **Where:** Repo for the engine; case study on the portfolio site (HTML/PDF); FastAPI + HTMX demo + review queue deployed (Fly.io, matching the EDI Pre-flight piece's pattern).
- **URL structure:** `remittance-parser.fly.dev` (or portfolio subpath).
- **How a prospect finds it:** Linked from Deduction Recovery and Trade Spend pieces as the "how the data gets in" companion; LinkedIn; ops people Googling "parse remittance advice PDF" / "reconcile retailer deductions."

#### Simulated Data Sources

Remittance advices "downloaded from" retailer/distributor AP portals: **Walmart, Costco, UNFI, KeHE** — four distinct layouts. UNFI and KeHE are kept as separate formats deliberately: they're different distributor relationships with different remittance structures and different promo-deduction code schemes, and a specialty food buyer recognizes them as separate worlds, not interchangeable. Each rendered with realistic messiness — multi-page stubs, inconsistent column naming, reason codes that don't map cleanly to the ERP. The scanned/image stub that justifies the OCR path is assigned to **one of the distributors** (an older image-based remittance export), not Costco — Costco remits through its portal (IWS), so a scanned Costco artifact would read as wrong to an ops person. All four reconcile against the existing Cinderhaven invoice/AR records.

### 5. Skills Demonstrated

- Document AI / OCR — getting structured data out of unstructured PDFs (the headline new skill)
- Handling heterogeneous source formats with one pipeline
- Deterministic validation design — balancing math + reason-code mapping as the trust signal, instead of black-box model confidence (the production-maturity differentiator)
- Human-in-the-loop review queue design — knowing exactly which extractions to escalate and why
- Reconciliation logic against existing financial records
- Domain fluency: deduction reason codes, dispute windows, distributor remittance formats

### 6. Foot-in-the-Door Offering

- **Offering name:** Remittance Reconciliation Setup (or "Deduction Intake Pipeline")
- **Format:** Fixed-fee build — set up the parser against the client's actual remittance formats, deliver a populated, reconciled ledger.
- **Price range:** $12K–$25K depending on number of distinct formats.
- **What the client gets:** A working parser tuned to their retailers/distributors, a back-populated deduction ledger, and a standing "dispute these before they expire" output.
- **Why this piece is the sales collateral:** The CFO sees their own pain — the PDF pile — turned into recoverable dollars on a clock. The recovery figure in the case study self-justifies the fee.

#### Client Lift

- **What the client has to do:** One kickoff call + hand over a sample of their remittance PDFs and read access to invoice/AR records. That's it.
- **What we need from them:** ~20–50 sample stubs per format, the invoice records to reconcile against, and their internal reason-code list if one exists.

#### The DIY Defense

- Every retailer/distributor format is different and they change without notice — a one-off script breaks on the next remittance run. The value is a pipeline built to absorb format drift, not a parser for today's PDF.
- Reason codes don't map cleanly to anything in the ERP; the mapping table is tribal knowledge that has to be *built*, and it's the hard part.
- "Just use OCR" gets you unstructured text strings, not a financial ledger — and raw model confidence will happily pay out a wrong number at 99% certainty. What makes this trustworthy isn't the text pull; it's the **deterministic balancing logic** that refuses to verify a row unless the math closes to the penny, plus the persistent reason-code mapping architecture that turns shifting layouts into consistent entries. That's the part a one-off script never has.

### 7. Marketing / Distribution

- **Portfolio integration:** Sits in a cluster with Deduction Recovery and Trade Spend Leakage as the "deduction lifecycle" — this is the intake stage. Cross-link all three.
- **LinkedIn:** "Your deductions arrive as PDFs. Your dispute window doesn't wait." Lead with the forfeit-by-calendar number.
- **SEO / organic:** "parse remittance advice," "reconcile retailer deductions," "UNFI/KeHE deduction codes," "automate AP remittance."
- **Shareability:** The drop-a-stub demo is the shareable artifact — ops people will test their own format and forward it.
- **Lead capture:** Keep the demo open. Optionally gate the full case study PDF behind an email; lean open given the buyer's skepticism of marketing gates.

### 8. Competitor / Existing Content Scan

- **What exists:** Enterprise AP-automation suites (high-end, ERP-coupled, built for huge AP volumes) and generic OCR/IDP tools that extract text but know nothing about retail deductions.
- **What's missing:** Nothing pitched at a $25M–$50M food brand that understands *deduction reason codes and dispute windows specifically*. The enterprise tools are overkill and over-priced; the generic OCR tools don't speak the domain.
- **Your angle:** Specialty-food-specific deduction intake — domain-aware classification + dispute-clock awareness, sized for a lean brand without an AP automation budget.

### 9. Cinderhaven Integration

- **Extends the dataset** with a new asset: synthetic remittance stubs in four formats, reconcilable against the *existing* Cinderhaven invoice/AR/chargeback records. No new financial reality invented — the stubs must add up to the already-canonical numbers.
- **Reuses** the deduction/chargeback records already built (3,357 chargebacks, ~$3.6M/yr all-in trade spend). The stubs are a new *view* of money already in the dataset, not new money.
- **Same retailers** (Walmart, Costco, Whole Foods, UNFI, KeHE) — no new trading partners introduced.
- **Consistency requirement:** The reconciled ledger output must tie exactly to existing Cinderhaven figures. This is the standing "consistent numbers across pieces" rule and it's load-bearing here.

### 10. Tactical Notes

- Build the synthetic stubs *first* and make them realistically ugly — multi-page, inconsistent headers, at least one scanned image. A clean synthetic PDF undersells the whole problem.
- Get reason codes right per source. UNFI promo deduction codes ≠ KeHE codes ≠ Walmart codes. Wrong codes = instant credibility loss with an AP person.
- Show the failure mode honestly via the **validation loop**, not a confidence bar: a row is verified only when `net + Σ deductions = gross` balances and every code maps; everything else escalates. Claiming perfect extraction is the tell of someone who hasn't done it.
- Reconcile to the existing Cinderhaven numbers — do not let parsed totals drift from the canonical ~$3.6M/yr all-in trade spend.

#### The Credibility Marker

Two markers, both practitioner-level. First: knowing that deductions have a **dispute window** and that the operational disaster isn't the deduction itself — it's the data arriving after the window closes. Generic data people parse the PDF; a practitioner reconciles it *against the clock*. Second: knowing not to trust a model's confidence on a financial figure — building the **arithmetic check** (`net + Σ deductions = gross`) as the real gate. "We trust the math, not the model" is the line that separates someone who has run a document pipeline in production from someone who has only demoed one.

#### Data Paranoia / Security

- **What's sensitive:** Remittance stubs expose net pricing, deduction structures, and distributor terms — exactly what a food brand least wants an outsider seeing.
- **How the narrative reassures:** Built to run on obfuscated SKUs and anonymized retailer labels; parser can run in the client's environment; case study uses synthetic Cinderhaven data so no real margins are ever shown.

### 11. Open Questions

*All four resolved (June 4, 2026 — incorporating external review):*

- [x] **Demo surface → FastAPI + HTMX.** Decided on function, not just tool-variety: the review queue *is* a side-by-side PDF viewer + editable form that highlights flagged rows, which is clunky in Streamlit and snappy in HTMX. Also avoids a third Streamlit piece.
- [x] **OCR engine → PaddleOCR (or Marker) + LLM extraction, not raw Tesseract.** Tesseract garbles multi-column financial tables. Privacy story preserved via a local layout parser or a VPC-hosted LLM rather than Tesseract-as-local-compromise.
- [x] **Number of formats → four (Walmart, Costco, UNFI, KeHE).** UNFI and KeHE kept as separate formats: different distributor relationships, different remittance structures, different promo-code schemes, and a food buyer reads them as distinct worlds. The marginal synthetic-data work is worth the buyer recognition.
- [x] **Standalone vs folded → standalone, deeply coupled.** Document AI is a headline portfolio capability and gets buried if it lives inside Deduction Recovery. Keep it as its own asset; make its output ledger the direct raw input to the Deduction Recovery code.

### 12. Build Estimate

- **Effort level:** Medium.
- **Dependencies:** Existing Cinderhaven invoice/chargeback records (built). No dependency on the in-progress Dimension & Weight piece.
- **New skills required:** Layout-aware OCR + LLM document extraction with a deterministic validation layer — new to the published portfolio. This is the point of the piece.

#### Out of Scope

- Full AP-automation / payment-processing workflow — this is intake + reconciliation, not an AP system.
- Automated dispute *filing* — the piece flags what to dispute; it does not submit disputes to retailer portals.
- General-purpose document parsing — this is remittance stubs specifically, not a "parse any CPG document" engine (that's a separate backlog item).

---

*Brief drafted June 4, 2026; revised same day with external review folded in. All open questions resolved — ready for build when you call it.*
