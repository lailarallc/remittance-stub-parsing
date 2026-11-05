# Remittance Stub Parsing — Handoff Log

Session-by-session state. Updated by /log mid-session and /wrap at
session end.

For durable choices, see DECISIONS.md.
For the current work arc, see PLAN.md.
For things that didn't work, see FAILURES.md.

---

## 2026-06-25 — Session wrap: reason code panel, factual fix, traffic-light color elimination

**Started from:** Prior session's /wrap was incomplete (compacted mid-wrap). HANDOFF/FAILURES needed updating.

**Did:** Completed prior /wrap. Added reason code reference panel + instructional hints to review queue. Fixed factual error in case study closing section ($207K breakdown). Full traffic-light color audit and elimination — removed all semantic green/red color signaling, deleted 6 CSS variables, unified all elements to navy/ink/white. Deployed to Fly.io (third attempt after two depot builder timeouts).

**State:** 206 tests passing. All commits pushed and deployed at remittance.lailarallc.com. No active arc. Zero traffic-light color signaling remaining.

**Next:** No planned work. Next /improve due 2026-07-08.

---

## 2026-06-25 — Session wrap: CSS width fixes, review panel split, pricing removal

**Started from:** Project built, deployed, reviewed. No active arc. 206 tests passing, live at remittance.lailarallc.com.

**Did:** Five CSS/template fixes, all pushed and deployed:
1. Diagnosed content width — `--content-max-width` already 1200px, no 900px anywhere. First attempted widening all 660px text to 1200px — reverted (unreadable paragraphs). Correct fix: text to 800px.
2. Widened review form panel — `.split-layout` grid from `3fr 2fr` (60/40 PDF/form) to `2fr 3fr` (40/60). Fixes truncated reason code descriptions.
3. Widened 9 text containers from 660px to 800px + chart from 700px to 800px. Closes text/data visual gap.
4. Fixed table column alignment — `col-amount` gets `nowrap` + `min-width: 100px`, `report-code` gets `word-break: break-all`. Applied to web CSS and PDF template.
5. Removed pricing sentence from case study closing section (what_this_means.html).

**State:** 206 tests passing. 6 commits pushed and deployed. Live at https://remittance.lailarallc.com. No active arc. Untracked: review.yaml, screenshots/.

**Next:** No planned work. Next /improve due 2026-07-08.

---

## 2026-06-24 — Session wrap: exec-readiness fixes + case study copy improvements

**Started from:** Project built, deployed, reviewed. All 206 tests passing. No active arc — polish pass for exec readiness.

**Did:** Two batches of exec-readiness fixes, both deployed to Fly.io:
1. **Exec-readiness (8 steps):** Added site-wide nav bar (Tour/Explore/Review/Case Study) to base.html. Changed /report default to show_all=true. Fixed British spellings (totalling→totaling, normalises→normalizes, Labour→Labor). Fixed singular/plural bugs for count=1 cases (formats, stubs, seconds, days). Fixed design system violations (issues box pink fill→neutral with red left border, content max-width 900→1200px). Renamed "Broken" badge to "Test Case" on explore grid. Updated 2 tests for new defaults.
2. **Case study copy (6 steps):** Replaced landing page hero subtitle with longer narrative. Reordered case study sections (margin_math before evidence). Created new closing section "What This Means for a $25M Brand" (what_this_means.html). Added to both HTML and PDF templates.

**State:** 206 tests passing. Two commits pushed and deployed: `8eab878` (exec-readiness), `bf2a7d2` (case study copy). Live at https://remittance.lailarallc.com. No active arc.

**Next:** No planned work. Next /improve due 2026-07-08.

---

## 2026-06-08 23:58 — Session wrap: eliminate inline JS, strict CSP

**Started from:** Project fully built, deployed, reviewed. Previous /improve deferred item: refactor inline onclick handlers so CSP can drop 'unsafe-inline'.

**Did:** Moved all tour logic from inline script in tour.html into app.js with event delegation. Removed onclick attributes from 6 buttons (tour.html + case_study.html). Converted inline style="display:none" to .is-hidden CSS class. Removed 'unsafe-inline' from script-src and style-src. Replaced BaseHTTPMiddleware with pure ASGI middleware (BaseHTTPMiddleware silently dropped headers through uvicorn).

**State:** 206 tests passing. CSP enforces script-src 'self'; style-src 'self' — no 'unsafe-inline'. Tour and report pages fully functional. 1 commit on main, not pushed, not redeployed.

**Next:** Push to origin, redeploy to Fly.io, verify CSP header on live site via curl. Next /improve due 2026-07-08.

---

## 2026-06-08 — First /improve pass: 6 fixes across security, docs, and path hygiene

**Started from:** All 9 units built, 206 tests passing, deployed to Fly.io, code review complete. First /improve run.

**Did:** Full audit (structural, security, dependency, workflow files). Found 2 critical + 4 important + 2 nice-to-have issues. Fixed all actionable items in 4 commits:
1. README rewritten from "scaffolded, not yet built" to actual deployed state
2. Self-hosted htmx 2.0.4 + htmx-ext-sse 2.2.3 from unpkg CDN into static/js/; added Content-Security-Policy middleware
3. Error messages in report.py no longer leak internal filesystem paths; source_file field stores filename only (not absolute path) across extractor + 4 generators
4. Archived completed arc in PLAN.md, added improvement history entry

**Dependency audit:** pip-audit found 12 CVEs in 6 packages — all transitive from other projects sharing this venv (flask, aiohttp, pyjwt, werkzeug, diskcache). None are direct dependencies.

**State:** 206 tests passing. 4 commits on main (not pushed). No active arc. Project is built, deployed, reviewed, and improved.

**Deferred:** Refactor inline onclick handlers to event listeners so CSP can drop 'unsafe-inline' (future /improve pass).

**Next:** Push to origin. Redeploy to Fly.io to pick up CSP header and self-hosted scripts. Next /improve due 2026-07-08.

---

## 2026-06-08 — Session wrap: 12-reviewer code review, 17 findings fixed, redeployed

**Started from:** All 9 units built, 206 tests passing, deployed to Fly.io. HANDOFF.md said "Run /ce:review for code quality pass."

**Did:** Full /ce:code-review with 12 parallel reviewer personas (6 always-on + 6 conditional). Raw output: ~75 findings across reviewers. After dedup/merge: 18 findings (1×P0, 6×P1, 8×P2, 3×P3). Fixed 17 of 18 — #18 (SQLite ledger not wired to web routes) is by-design.

Key fixes:
- **P0:** Path traversal in all file-serving endpoints — added `resolve().is_relative_to()` checks
- **P1:** Sync blocking in async handlers (asyncio.to_thread), Dockerfile non-root user, Claude API 30s timeout, YAML caching (lru_cache), threading.Lock on review cache, form-field iteration cap (200)
- **P2:** Eliminated double PDF file open (extract_stub_with_text), removed unused import, payment_date made Optional, WeasyPrint URL fetcher restricted, narrowed exception types, cached _scan_stubs, added 10MB file size limit
- **P3:** Fixed _format_compact negative sign, normalized keHE case detection

Committed as `9b74782`, pushed to origin, redeployed to Fly.io. Updated project-health.md (Tests=yes, code-review=yes, date=2026-06-08).

**State:** All routes live at https://remittance.lailarallc.com. 206 tests passing. All Definition of Done items complete. Code review complete. Container now runs as non-root.

**Next:** Run /improve when due (set next-improve-due date). Consider setting ANTHROPIC_API_KEY on Fly.io. Consider /ce:compound to extract learnings.

---

## 2026-06-08 19:17 — Session wrap: visual verification, font self-hosting, Fly.io deploy with custom domain

**Started from:** All 9 units built (U1–U9), 206 tests passing. No visual verification, no self-hosted fonts, not deployed.

**Did:** Verified all 5 routes in browser. Fixed header brand to "Lailara LLC". Self-hosted Playfair Display + Source Sans 3 woff2. Deployed to Fly.io — fixed missing sse-starlette in requirements.txt. Added DNS records via Cloudflare API. SSL cert issued.

**State:** All routes live at https://remittance.lailarallc.com. 206 tests passing. All Definition of Done items complete. No ANTHROPIC_API_KEY on Fly (pdfplumber-only). project-health.md needs Tests column updated to "yes".

**Next:** Run /ce:review for code quality pass. Update project-health.md. Consider setting ANTHROPIC_API_KEY on Fly.

---

## 2026-06-08 19:16 — Deployed to Fly.io, custom domain remittance.lailarallc.com live with SSL

**What changed:** Deployed to Fly.io (IAD, shared-cpu-1x, 512MB). Fixed missing sse-starlette in requirements.txt that crashed the container. Added DNS records (A + AAAA) via Cloudflare API. SSL cert issued (Let's Encrypt, RSA+ECDSA).

**Why:** Final Definition of Done item — "Deployed with lailarallc.com subdomain." App now publicly accessible.

**State:** All routes live at https://remittance.lailarallc.com. Health check passing. No ANTHROPIC_API_KEY set (pdfplumber-only extraction). All 9 units complete, 206 tests passing, deployed. .claude/launch.json in .dockerignore (excluded from image).

**Next:** Run /ce:review for code quality pass before shipping.

---

## 2026-06-08 18:57 — Visual verification complete, brand name fix, font self-hosting

**What changed:** Visually verified all 5 routes in browser (landing, tour, explore, review, report). Fixed header brand from "Lailara" to "Lailara LLC". Self-hosted Playfair Display + Source Sans 3 as woff2 in app/static/fonts/ with @font-face in main.css and PDF template.

**Why:** HANDOFF.md listed visual verification as the first next step. Fonts were using system fallbacks; design system requires self-hosted fonts with no Google Fonts CDN dependency.

**State:** All routes working, design system fonts loading correctly, zero console/server errors. 206 tests still passing. NOT yet deployed to Fly.io. .claude/launch.json added for preview tooling.

**Next:** Fly.io deploy — provision app, set ANTHROPIC_API_KEY secret, deploy, configure lailarallc.com subdomain. Then run /ce:review.

---

## 2026-06-08 — Full 9-unit build complete (U1–U9), 206 tests passing

**Started from:** Plan complete, no code. All 9 implementation units defined in docs/plans/.

**Did:**
1. **U1 Foundation** — pyproject.toml, requirements.txt, Pydantic models (RetailerFormat, DeductionCategory, RemittanceStub, ValidationResult, ReconciliationResult), 4 retailer reason-code YAML configs, 20 model tests
2. **U2 Synthetic stubs** — FPDF2 generators for Walmart, Costco, UNFI, KeHE with clean + broken variants (arithmetic mismatch, unmapped codes, multi-page). 15 PDFs, 20 tests. sanitize_for_pdf() to handle encoding.
3. **U3 PDF extraction** — pdfplumber extractor with detect_format(), per-retailer column mapping, multi-page table merging. 47 tests.
4. **U4 LLM extraction** — Claude Haiku 4.5 via forced tool_choice (record_deductions). Hybrid pipeline: pdfplumber first (free), LLM second (picks winner by deduction count). 30 tests.
5. **U5 Validation + ledger** — Arithmetic check (net + deductions = gross), reason-code validation, SQLite ledger (WAL mode, Decimal-as-string), reconciliation against Cinderhaven SSOT ($3.5M/yr, 864 chargebacks, 90-day window). 37 tests.
6. **U6 FastAPI skeleton** — Routes for demo, tour, review, report. Jinja2 templates, HTMX partials, SSE via sse-starlette. 15 tests.
7. **U7 Interactive demo** — Guided tour (SSE streaming), free exploration, review queue with side-by-side PDF viewer + editable form. 19 tests.
8. **U8 Case study** — Dynamic report with hook/proof/evidence/margin_math sections. WeasyPrint PDF export. Separate templates for web (extends base) and PDF (standalone). 18 tests.
9. **U9 Polish + deploy config** — Lailara design system CSS (Canvas, Navy, Hong Kong teal, Playfair Display + Source Sans 3), Dockerfile (python:3.13-slim + pango/cairo), fly.toml (IAD, 8080, health check).

**Artifacts:** 62 source files, 206 passing tests, 15 synthetic PDFs, 9 commits.

**Fixes during build:**
- pyproject.toml: `setuptools.backends._legacy:_Backend` → `setuptools.build_meta`
- Em-dash encoding in walmart.yml crashed on Windows; replaced with ASCII hyphen
- Costco.yml had mojibake (UTF-8 em-dash as 3 codepoints) that crashed FPDF2 latin-1 font
- Starlette 1.0.1 changed TemplateResponse signature; fixed to pass request as first positional arg
- Jinja2 `{% extends %}` inside `{% if %}` not allowed; split into web + PDF templates

**State:**
- All 9 units built and committed on main
- 206/206 tests pass
- Dockerfile and fly.toml ready
- NOT yet deployed to Fly.io
- Fonts not yet self-hosted (using system fallbacks)
- App not yet visually verified in browser

**Next:**
1. Visual verification: `uvicorn app.main:app --reload`, test all routes in browser
2. Self-host Playfair Display + Source Sans 3 (download woff2, serve from static/)
3. Fly.io deploy: provision app, set secrets, deploy, configure custom domain
4. Run /ce:review for code quality pass

---

## 2026-06-05 — Channel-profitability annual framing complete; trade-spend-leakage deploy blocked

**Started from:** Prior session completed figure reconciliation + multi-repo push (3/6). This session's goals: finish annual-framing pass on channel-profitability-analysis, trigger Fly.io deploy for trade-spend-leakage.

**Did:**
1. **Channel-profitability annual framing — COMPLETE.** Full data-layer conversion:
   - `generate_json.py`: Added `YEARS = 3` constant, divided all cumulative values (revenue, deductions, fines, disputes, events, hours) by 3. Added Q1 2027 data to snapshot constants (was in committed trends.json but missing from generator).
   - `channels.json` / `layers.json`: Now contain annual averages (e.g., national mass retailer revenue $3.6M/yr not $10.9M)
   - All 8 MDX narrative sections updated: prose figures match annual data layer
   - `test_prose_data.py`: All 21 expected values updated from cumulative to annual; all 34 checks pass
   - Built, deployed to Cloudflare Pages, pushed to GitHub
2. **Trade-spend-leakage deploy — BLOCKED.** `gh workflow run` failed (no `workflow_dispatch` trigger). Empty commit + push triggered on-push workflow, but Fly.io deploy failed on health check timeout. Diagnosed: app is suspended on Fly.io (not in deployed apps list on dashboard). Fix: `fly apps resume trade-spend-leakage` then redeploy.

**State:**
- channel-profitability-analysis: annual framing complete, deployed, pushed
- trade-spend-leakage: needs `fly apps resume` before deploy will succeed
- This repo (remittance-stub-parsing): clean, no code yet
- 3 repos still need pull-rebase from prior session (trade-spend-data-diagnostic, retailer-deduction-recovery, contract-to-cash)

**Next:**
1. Unsuspend trade-spend-leakage on Fly.io, redeploy
2. Pull-rebase 3 diverged repos, push
3. Start U1 build in this repo via /ce:work

---

## 2026-06-05 — Figure reconciliation + multi-repo push (3 of 6 complete)

**Started from:** Compacted session. Distressed repoint + narrative rewrite done, needed commit + report + push.

**Did:** Committed distressed repoint (`1a8de45`, 11 files). Diagnosed 5 figure mismatches between workbook and narrative docs — structural rate 10.8% was baseline ALL-IN mislabeled as structural (actual: 9.2%), vague count 967 was 36mo total not trailing-365 (actual: 318), no-PO % was wrong denominator. Reconciled all docs to workbook values (`25107c8`). Pushed 3 of 6 repos (cinderhaven-data-platform, remittance-stub-parsing, dimension-weight-integrity already pushed). 3 repos blocked by remote divergence from URL cleanup batch.

**State:**
- Pushed: cinderhaven-data-platform (3 commits), remittance-stub-parsing (4 commits), dimension-weight-integrity (already current)
- Blocked: trade-spend-data-diagnostic, retailer-deduction-recovery, contract-to-cash — all have remote URL cleanup commits that need pull-rebase
- Canonical guard: GREEN (864 chargebacks, $32.5M, $3.4M)
- This repo: clean, no code yet

**Next:** Pull-rebase 3 diverged repos (trade-spend-data-diagnostic, retailer-deduction-recovery, contract-to-cash), resolve README conflicts, push. Then start U1 build in this repo.

---

## 2026-06-05 — Distressed scenario infra built in cinderhaven-data-platform

**Started from:** Prior session left trade-spend-diagnostic with workbook clean but 5 narrative docs still stale. contract-to-cash og:meta fixed. This session's goal: build scenario-branch infrastructure so the diagnostic can have its exposé back without touching baseline data.

**Did:**
1. Committed trade-spend-diagnostic workbook rebuild (`88825ee` — 7 files)
2. Committed contract-to-cash og:meta fix (`ca6f31e` — 86.5¢/$17.8M)
3. Read-only narrative diagnosis: all 5 docs classified PROBLEM-DEPENDENT (need messy data, not just string replacement)
4. Blast-radius analysis: confirmed waste-only re-baseline is surgically achievable — revenue, structural trade, chargebacks all isolated
5. Phase 0: Studied v1 deduction generator machinery (PROFILES, VAGUE_TEMPLATES, double-dip injection, per-retailer rates)
6. **Phase 1 (Stage 1): Built distressed scenario in cinderhaven-data-platform** (`18d1b77`):
   - `seed_config.py`: SCENARIO flag + DISTRESSED_DEDUCTION_TYPES + VAGUE_TEMPLATES (additive, frozen blocks untouched)
   - `generate_distressed_scenario.py`: standalone script, copies baseline SQLite, replaces deductions/disputes with v1-style mess
   - `CINDERHAVEN_CANONICAL.md`: distressed figure table added below baseline block
   - `.gitignore`: data/*.db
   - Generated `data/cinderhaven_distressed.db` (gitignored artifact)

**Distressed scenario figures:**
- Waste: ~$965K/yr (excl promo_billback)
- Vague: 967 deductions, $419K/yr, 295 w/o PO link (30.5%)
- Double-dips: 3 / $19,062
- Ghost promos: 3,258 / $361K
- Recovery rate: 20.9%
- Baseline provably unchanged: 690 chargebacks, 46,414 orders, $32.54M scan revenue

**State:**
- cinderhaven-data-platform: committed at `18d1b77`, NOT pushed
- trade-spend-diagnostic: workbook committed at `88825ee`, 5 narrative docs UNCOMMITTED (waiting for Stage 2)
- contract-to-cash: og:meta committed at `ca6f31e`, NOT pushed
- This repo (remittance-stub-parsing): clean, no pending changes, no code yet

**Next (in order):**
1. **Stage 2 (user-gated):** Rewrite trade-spend-diagnostic's 5 narrative docs using distressed scenario figures. Shawn reviews distressed numbers first.
2. Push all repos in dependency order (cinderhaven-data-platform first)
3. Start U1 build in this repo via /ce:work

---

## 2026-06-05 — Guard verified, artifact audit clean, trade-spend diagnostic partially rebuilt

**Started from:** Session interrupted last night mid-commit. Needed to verify guard, audit rendered artifacts, rebuild trade-spend-diagnostic.

**Did:** Confirmed all 5 commits landed (nothing to redo). Verified freeze guard passes against live Postgres (GUARD GREEN, exit 0). Audited 6 shipped repos for stale rendered artifacts — no trade-cost figures baked in. Rebuilt trade-spend-data-diagnostic: re-exported SQLite from Postgres v2, fixed schema gaps (Kroger column, retailer_id compatibility), rebuilt workbook, recalibrated validation (59/59 pass). Identified contract-to-cash og:meta staleness. Confirmed "150 cases" = short-ship-cost. Confirmed retailer-deduction-recovery uncommitted changes don't conflict with canonical fix.

**State:**
- 4 doc/SSOT repos: committed, guard green, ready to push
- trade-spend-data-diagnostic: workbook + validation clean, code fixes applied, but 5 narrative docs still have old figures (README, EXECUTIVE_MEMO, walkthrough, DEFENSIBILITY, cinderhaven-data/README) — UNCOMMITTED
- contract-to-cash: og:meta fix identified, not applied
- This repo (remittance-stub-parsing): clean, no pending changes

**Next:** Two follow-up sessions:
1. trade-spend-data-diagnostic narrative rewrite — rewrite 5 docs with v2 figures (workbook/data is clean, only prose). Commit.
2. contract-to-cash og:meta fix — update index.html meta tags. Quick commit.
3. Push all 6 repos in dependency order (cinderhaven-data-platform first).
4. Then start U1 build in this repo.

---

## 2026-06-04 — Phase A canonical figures verified and locked

**What changed:** Queried cinderhaven-db Postgres SSOT directly (via flyctl proxy). Verified all-in trade cost, chargeback count, and data window. Found that legacy figures ($5.4M / 464 / 18 months) were wrong on all three counts. Also found that the May 2026 diagnostic figures ($7.17M / 26.1%) are stale — Postgres was regenerated with different seed_config.py parameters (trade_spend_pct values dropped ~50%).

**Locked canonical figures:**
- All-in trade cost: $3.4M annualized / $10.3M over 36 months / $3.5M trailing-52w
- Rate: ~10.8% of trailing-52w scan revenue ($32.5M)
- Components: structural trade ($8.8M/36mo) + operational waste ($1.4M/36mo, excl promo_billback)
- Chargebacks: 864 (690 retailer + 174 distributor, no reversals)
- Window: 2024-01-01 to 2027-01-02 (36 months, not 18)
- EBITDA check: plausible (24.7% trade+EBITDA, 75.3% COGS+SGA)

**What 464 actually was:** DPI Northwest's deduction count in the deduction-recovery project's summary.json. Misquoted as "total chargebacks" in the remittance brief.

**State:** Phase A (verify + report) complete. DECISIONS.md and FAILURES.md updated. PLAN.md pre-work task marked done, stale figures replaced. No code yet.

**Phase B (propagate) — first action next session:**
1. Grep this repo for $5.4M / 464 / "18 month" / $7.2M / 7,174,939 — print all hits, replace confirmed matches in: portfolio brief, requirements doc, plan doc, PLAN.md scope section
2. Do NOT edit other repos — but these external pieces cite stale figures and need separate sessions:
   - trade-spend-data-diagnostic (re-export SQLite, re-lock all 15+ hardcoded refs)
   - dimension-weight-integrity (cites "464 chargebacks" and "$5.4M")
   - Possibly: deduction-recovery, contract-to-cash, where-the-money-comes-from
3. Open question: headline number for case study copy — "$3.4M annualized" vs "$10.3M over 36 months" vs trailing-52w "$3.5M"
4. After Phase B propagation, run /ce:work to start U1

**Next concrete action:** grep + replace stale figures in this repo (Phase B), then /ce:work for U1.

---

## 2026-06-04 17:35 — Project initialized

**Started from:** New project setup via /new-project.

**Did:** Created repo, set up CLAUDE.md/DECISIONS.md/HANDOFF.md/PLAN.md/
FAILURES.md, configured project structure. Brainstorm brief already
exists at portfolio_project_brief_remittance_parsing.md.

**State:** Foundation in place. Stack set to Python (specific libraries
TBD). Ready for /clarify to scope the work.

**Next:** Run /clarify to reach 95% confidence on requirements, then
/ce:brainstorm and /ce:plan.

---

## 2026-06-04 17:50 — /clarify completed

**What changed:** Project scaffolded and /clarify completed. All five deliverables confirmed, scope boundaries locked down, five architecture decisions recorded.

**Why:** Need 95% confidence on requirements before brainstorm and planning. Confirmed all 5 deliverables required, dropped OCR pipeline, scoped demo to 4 known formats only, confirmed broken stubs for review queue, confirmed demo as educational walkthrough.

**State:** Scaffold complete (git, GitHub remote, all state files). PLAN.md has confirmed goal, scope, and definition of done. DECISIONS.md has 5 architecture decisions. No code yet. Tech stack is Python; all libraries and frameworks TBD.

**Next:** Run /ce:brainstorm to spec out architecture and tool choices.

---

## 2026-06-04 19:15 — /ce:brainstorm + /ce:plan completed, doc review done

**What changed:** Full requirements doc written (docs/brainstorms/), 9-unit implementation plan written (docs/plans/), tech stack decided via research agents, doc review applied 3 auto-fixes and surfaced 21 findings (2 at P0).

**Why:** Completing the Medium-tier workflow: /clarify → /ce:brainstorm → /ce:plan. Plan now defines the full build from foundation through deployment with researched tech choices.

**State:** Plan complete at docs/plans/2026-06-04-001-feat-remittance-stub-parsing-plan.md. 9 implementation units (U1-U9). Tech stack decided: pdfplumber, Claude API + Pydantic, FastAPI + HTMX + Jinja2, WeasyPrint, FPDF2, Fly.io. No code yet. Two P0 findings from doc review need attention before implementation:
1. **CRITICAL: $5.4M figure may be stale.** Feasibility reviewer found cinderhaven-data README shows $7.2M (26.1%) all-in trade cost and ~381-391 chargebacks, not $5.4M/464. Must verify against current Postgres SSOT and update plan, PLAN.md, requirements doc, and brief before U1.
2. R24 in Requirements section should preserve origin's open framing (Fly.io decision is correctly documented in Key Technical Decisions section).
3. SSE requires sse-starlette package (not built into FastAPI) — add to dependencies in U1.

**Next:** Start new session. First action: verify Cinderhaven canonical figures against current SSOT (query Postgres), update all docs with correct numbers, then run /ce:work on the plan.

---
