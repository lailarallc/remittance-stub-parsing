"""Client-mode CLI for remittance-stub-parsing.

Parses a client's own remittance PDFs (built-in formats OR new client formats
dropped in as plugins), reconciles them against the client's AR ledger, and
produces a branded, provenance-footed recoverable-deduction summary — validated,
never committed, never deployed.

Intake here is PDFs + config (not a single tabular file), so the preflight is
PDF-aware: every PDF must detect to a known format plugin, and a reference AR
ledger must be present. A file that doesn't detect (or a missing ledger) yields a
branded Data Readiness Report instead of results.

To add a client's remittance format: drop ``format_configs/<name>.yml`` +
``reason_codes/<name>.yml`` into the client config dir (see INPUT-SPEC.md) — no
code change. Point ``engagement.yml`` at that dir.

Usage:
    python client_mode.py --config engagement.yml --input client-data/stubs/ \
        --out client-output [--final]
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

from lailara_engagement import (
    Finding,
    PreflightReport,
    build_provenance,
    load_config,
    write_report,
)
from lailara_engagement import palette as P
from lailara_engagement.provenance import InputRef, Provenance

from src.extraction.pdf_extractor import extract_with_plugin
from src.extraction.plugins import DEFAULT_CONFIG_DIR, detect_plugin, discover_plugins
from src.ledger.reconciliation import reconcile_stub
from src.models import DeductionCategory, retailer_display_name

TOOL = "remittance-stub-parsing"
TOOL_VERSION = "1.0"


def _first_page_text(pdf_path: Path) -> str:
    import pdfplumber
    with pdfplumber.open(str(pdf_path)) as doc:
        if not doc.pages:
            return ""
        return doc.pages[0].extract_text() or ""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_reference_ledger(path: Path) -> dict:
    """Load the client AR ledger: {invoice_number: {amount: Decimal, date: date}}.

    Accepts JSON ({"invoices": {...}}) or CSV/XLSX (invoice_number, amount, date)
    via the tolerant reader.
    """
    if not path.exists():
        return {}
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        out = {}
        for inv, rec in data.get("invoices", {}).items():
            out[str(inv)] = {"amount": Decimal(str(rec["amount"])),
                             "date": date.fromisoformat(rec["date"])}
        return out
    from lailara_engagement import read_table
    read = read_table(str(path))
    cols = {c.lower(): c for c in read.columns}
    inv_c = cols.get("invoice_number") or cols.get("invoice") or read.columns[0]
    amt_c = cols.get("amount")
    date_c = cols.get("date")
    out = {}
    for _, row in read.frame.iterrows():
        inv = str(row[inv_c]).strip()
        if not inv:
            continue
        try:
            amt = Decimal(str(row[amt_c]).strip()) if amt_c else Decimal("0")
        except Exception:
            amt = Decimal("0")
        d = None
        if date_c:
            try:
                d = date.fromisoformat(str(row[date_c]).strip())
            except Exception:
                d = None
        out[inv] = {"amount": amt, "date": d}
    return out


def _config_dir(config) -> Path:
    raw = config.raw.get("format_config_dir") or config.basis.get("format_config_dir")
    return Path(raw) if raw else DEFAULT_CONFIG_DIR


def _preflight(pdfs: list[Path], config_dir: Path, ledger_path: Path,
               ledger: dict) -> PreflightReport:
    findings: list[Finding] = []
    disclosures: list[str] = []
    known = {p.name for p in discover_plugins(config_dir)}
    disclosures.append(f"Known format plugins: {', '.join(sorted(known)) or '(none)'}")

    if not pdfs:
        findings.append(Finding(severity="error", category="no-input",
                                message="No remittance PDFs found in the input directory.",
                                spec_ref="INPUT-SPEC §1"))
    unrecognized = []
    for pdf in pdfs:
        try:
            plugin = detect_plugin(_first_page_text(pdf), config_dir)
        except Exception as exc:
            plugin = None
            disclosures.append(f"Reader: {pdf.name}: {exc}")
        if plugin is None:
            unrecognized.append(pdf.name)
    if unrecognized:
        findings.append(Finding(
            severity="error", category="unrecognized-format",
            message=(f"{len(unrecognized)} PDF(s) did not match any known format "
                     f"plugin — add a format_configs/<name>.yml for each"),
            examples=tuple(unrecognized[:5]), total=len(unrecognized),
            spec_ref="INPUT-SPEC §2",
            assumption="each remittance format needs a header_pattern config to be detected"))
    if not ledger:
        findings.append(Finding(
            severity="warning", category="no-reference-ledger",
            message=(f"No reference AR ledger loaded from {ledger_path} — deductions "
                     f"cannot be reconciled; recoverable totals will be unavailable"),
            spec_ref="INPUT-SPEC §3"))

    has_error = any(f.severity == "error" for f in findings)
    has_warning = any(f.severity == "warning" for f in findings)
    status = "failed" if has_error else ("warnings" if has_warning else "clean")
    return PreflightReport(
        tool=TOOL, status=status, passed=not has_error, findings=findings,
        disclosures=disclosures, column_mapping={}, n_rows=len(pdfs), n_cols=0,
        spec_version=TOOL_VERSION,
    )


def run(config_path: str, input_path: str, out_dir: str, *, final: bool = False) -> dict:
    config = load_config(config_path)
    config_dir = _config_dir(config)
    ledger_raw = config.raw.get("reference_ledger") or config.basis.get("reference_ledger")
    ledger_path = Path(ledger_raw) if ledger_raw else Path("data/cinderhaven_reference.json")
    ledger = _load_reference_ledger(ledger_path)

    in_dir = Path(input_path)
    pdfs = sorted(in_dir.glob("*.pdf")) if in_dir.is_dir() else ([in_dir] if in_dir.suffix == ".pdf" else [])

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    input_refs = [InputRef(filename=p.name, sha256=_sha256(p), n_rows=0, n_cols=0) for p in pdfs]
    report = _preflight(pdfs, config_dir, ledger_path, ledger)
    provenance = build_provenance(
        tool=TOOL, tool_version=TOOL_VERSION,
        inputs=input_refs or [InputRef(filename="(none)", sha256="", n_rows=0, n_cols=0)],
        config=config,
        validation_status=("clean" if report.status == "clean"
                           else f"proceeded with warnings ({report.n_warnings})"
                           if report.status == "warnings" else "blocked — data not ready"),
    )
    if not report.passed:
        paths = write_report(report, config, str(out), provenance=provenance,
                             draft=not final, basename="data-readiness-report",
                             title="Remittance Data Readiness Report")
        return {"status": "blocked", "readiness_report": paths["html"]}

    # Dispute-window math is "as of now" = the reconciliation/report date; an old
    # as_of_date-only config falls back to its (data) date, preserving prior behavior.
    as_of = config.report_date or config.as_of_date
    dispute_window = int(config.basis["dispute_window_days"])

    total_deductions = Decimal("0")
    within_window = Decimal("0")
    past_window = Decimal("0")
    by_format = defaultdict(lambda: {"stubs": 0, "deductions": 0, "amount": Decimal("0")})
    by_category = defaultdict(lambda: Decimal("0"))
    stub_count = 0

    for pdf in pdfs:
        plugin = detect_plugin(_first_page_text(pdf), config_dir)
        stub = extract_with_plugin(pdf, plugin)
        recon = reconcile_stub(stub, ledger, dispute_window_days=dispute_window,
                               stub_id=pdf.name, as_of_date=as_of)
        stub_count += 1
        fmt = retailer_display_name(stub.retailer)
        by_format[fmt]["stubs"] += 1
        reason_codes = plugin.reason_codes
        for d in stub.deductions:
            total_deductions += d.amount
            by_format[fmt]["deductions"] += 1
            by_format[fmt]["amount"] += d.amount
            cat = reason_codes.get(d.reason_code, {}).get("category", DeductionCategory.UNKNOWN.value)
            by_category[cat] += d.amount
        if recon.dispute_window_days_remaining is not None and recon.dispute_window_days_remaining <= 0:
            past_window += recon.unmatched_amount
        else:
            within_window += recon.unmatched_amount

    recoverable = within_window + past_window
    summary = {
        "data_as_of": config.as_of_date.isoformat(),
        "report_date": config.report_date.isoformat() if config.report_date else "",
        "computed_as_of": as_of.isoformat(),
        "dispute_window_days": dispute_window,
        "window_label": config.basis.get("window_label", ""),
        "stub_count": stub_count,
        "format_count": len(by_format),
        "total_deduction_amount": str(total_deductions),
        "recoverable_total": str(recoverable),
        "within_window": str(within_window),
        "past_window": str(past_window),
        "by_format": {k: {**v, "amount": str(v["amount"])} for k, v in by_format.items()},
        "by_category": {k: str(v) for k, v in by_category.items()},
    }
    json_dir = out / "json"
    json_dir.mkdir(parents=True, exist_ok=True)
    (json_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    report_path = out / "remittance-recovery-summary.html"
    report_path.write_text(_summary_html(config, summary, provenance, draft=not final),
                           encoding="utf-8")
    return {"status": "ok", "recoverable": str(recoverable), "stub_count": stub_count,
            "report": str(report_path), "summary_json": str(json_dir / "summary.json")}


def _fmt(v) -> str:
    return f"${Decimal(str(v)):,.2f}"


def _summary_html(config, s, provenance: Provenance, *, draft: bool) -> str:
    esc = html.escape
    wl = s.get("window_label") or ""
    fmt_rows = "".join(
        f"<tr><td>{esc(k)}</td><td class=num>{v['stubs']}</td>"
        f"<td class=num>{v['deductions']}</td><td class=num>{_fmt(v['amount'])}</td></tr>"
        for k, v in sorted(s["by_format"].items(), key=lambda kv: Decimal(kv[1]["amount"]), reverse=True))
    cat_rows = "".join(
        f"<tr><td>{esc(k)}</td><td class=num>{_fmt(v)}</td></tr>"
        for k, v in sorted(s["by_category"].items(), key=lambda kv: Decimal(kv[1]), reverse=True))
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width, initial-scale=1">
<title>Remittance Recovery — {esc(config.client_name)}</title><style>{_css(draft)}</style></head>
<body class="{' ll-draft' if draft else ''}"><main class=ll-page>
<header class=ll-header>
  <div class=ll-eyebrow>Lailara LLC · Remittance Recovery</div>
  <h1 class=ll-title>Recoverable Deductions</h1>
  <div class=ll-client>
    <div><span class=ll-k>Client</span> {esc(config.client_name)}</div>
    <div><span class=ll-k>Engagement</span> {esc(config.engagement_id)}</div>
    <div><span class=ll-k>Data as of</span> {esc(s['data_as_of'])}</div>
    <div><span class=ll-k>Reconciled as of</span> {esc(s['computed_as_of'])}</div>
    <div><span class=ll-k>Dispute window</span> {s['dispute_window_days']} days{(' · ' + esc(wl)) if wl else ''}</div>
  </div>
</header>
<section class=ll-banner>
  <div class=ll-score>{_fmt(s['recoverable_total'])} recoverable</div>
  <div>{_fmt(s['within_window'])} within window · {_fmt(s['past_window'])} past window
       · {s['stub_count']} stubs across {s['format_count']} formats</div>
</section>
<section class=ll-section>
  <h2 class=ll-h2>By format</h2>
  <table class=ll-table><thead><tr><th>Format</th><th>Stubs</th><th>Deductions</th>
  <th>Amount</th></tr></thead><tbody>{fmt_rows}</tbody></table>
</section>
<section class=ll-section>
  <h2 class=ll-h2>By deduction category</h2>
  <table class=ll-table><thead><tr><th>Category</th><th>Amount</th></tr></thead>
  <tbody>{cat_rows}</tbody></table>
  <p class=ll-note>Recoverable = unreconciled deductions across both dispute-window
  buckets. Dispute windows computed as of {esc(s['computed_as_of'])} (the report date —
  not the {esc(s['data_as_of'])} data-window end, and not the wall clock) against a
  {s['dispute_window_days']}-day window from config.</p>
</section>
{provenance.to_html()}
</main></body></html>"""


def _css(draft: bool) -> str:
    draft_css = (
        ".ll-draft::before{content:'DRAFT';position:fixed;top:50%;left:50%;"
        "transform:translate(-50%,-50%) rotate(-32deg);font-family:var(--s);"
        "font-size:22vw;font-weight:700;color:rgba(204,16,10,.06);z-index:0;"
        "pointer-events:none;white-space:nowrap}" if draft else ""
    )
    return f"""
:root{{--s:{P.LL_SERIF};--f:{P.LL_SANS}}}*{{box-sizing:border-box}}
body{{margin:0;background:{P.LL_CANVAS};color:{P.LL_TEXT};font-family:var(--f);line-height:1.6}}
.ll-page{{position:relative;z-index:1;max-width:{P.LL_MAX_WIDTH};margin:0 auto;padding:48px 24px}}
.ll-header{{border-bottom:1px solid {P.LL_GRIDLINE};padding-bottom:24px;margin-bottom:24px}}
.ll-eyebrow{{font-size:12px;letter-spacing:.04em;text-transform:uppercase;color:{P.LL_RED};font-weight:600}}
.ll-title{{font-family:var(--s);font-weight:700;color:{P.LL_INK};font-size:34px;margin:8px 0 16px}}
.ll-client{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px 24px;font-size:14px}}
.ll-k{{display:block;color:{P.LL_TEXT_SEC};font-size:11px;text-transform:uppercase;letter-spacing:.04em}}
.ll-banner{{border-radius:2px;padding:16px 20px;margin-bottom:32px;background:{P.LL_HK_SURFACE};color:{P.LL_HK_DARK}}}
.ll-score{{font-family:var(--s);font-weight:700;font-size:22px}}
.ll-section{{margin:0 0 32px}}
.ll-h2{{font-family:var(--s);font-weight:700;color:{P.LL_INK};font-size:22px;
margin:0 0 12px;padding-bottom:6px;border-bottom:1px solid {P.LL_GRIDLINE}}}
.ll-note{{font-size:13px;color:{P.LL_TEXT_SEC};margin-top:8px}}
.ll-table{{width:100%;border-collapse:collapse;font-size:14px}}
.ll-table th{{text-align:left;background:{P.LL_CHICAGO};color:#fff;padding:8px 12px}}
.ll-table td{{padding:8px 12px;border-bottom:1px solid {P.LL_GRIDLINE}}}
.num{{text-align:right;font-variant-numeric:tabular-nums}}
.ll-provenance{{margin-top:40px;background:{P.LL_CARD_BG};color:{P.LL_CARD_TEXT};
padding:20px 24px;border-radius:2px;font-size:13px}}
.ll-prov-title{{font-family:var(--s);font-weight:700;font-size:16px;margin-bottom:8px}}
.ll-provenance div{{margin-bottom:4px;color:{P.LL_CARD_SUBTITLE}}}
.ll-provenance strong{{color:{P.LL_CARD_TEXT}}}
.ll-prov-inputs{{width:100%;border-collapse:collapse;margin-top:8px}}
.ll-prov-inputs th{{text-align:left;border-bottom:1px solid rgba(255,255,255,.12);padding:4px 8px;color:{P.LL_CARD_MUTED}}}
.ll-prov-inputs td{{padding:4px 8px;border-bottom:1px solid rgba(255,255,255,.08);color:{P.LL_CARD_SUBTITLE}}}
.ll-prov-brand{{margin-top:12px;font-family:var(--s);color:{P.LL_CARD_MUTED}}}
{draft_css}
@media print{{body{{background:#fff}}}}
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="remittance client mode")
    ap.add_argument("--config", required=True)
    ap.add_argument("--input", required=True, help="directory of client remittance PDFs")
    ap.add_argument("--out", default="client-output")
    ap.add_argument("--final", action="store_true")
    args = ap.parse_args(argv)
    result = run(args.config, args.input, args.out, final=args.final)
    if result["status"] == "blocked":
        print(f"BLOCKED — data not ready. See {result['readiness_report']}")
        return 3
    print(f"recoverable {result['recoverable']} across {result['stub_count']} stubs")
    print(f"report -> {result['report']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
