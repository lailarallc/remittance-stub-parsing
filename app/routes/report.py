"""Report routes: dynamic case study generation (HTML + PDF via WeasyPrint).

Builds a case study report from processed stubs. Visitors can see
a report for the stubs they explored, or generate the complete
Cinderhaven story with all 15 stubs. PDF export via WeasyPrint
degrades gracefully when WeasyPrint is unavailable (common on
Windows without system deps).
"""

import asyncio
import json
import logging
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Optional

import yaml
from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from src.extraction.pipeline import extract
from src.ledger.reconciliation import (
    ANNUAL_TRADE_SPEND,
    TOTAL_CHARGEBACKS,
    reconcile_stub,
)
from src.models import DeductionCategory, ValidationStatus, load_reason_codes
from src.validation.reason_codes import validate_stub

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/report")

STUBS_DIR = Path(__file__).parent.parent.parent / "stubs"
DATA_DIR = Path(__file__).parent.parent.parent / "data"
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _format_currency(value) -> str:
    """Format a number as currency with commas and 2 decimal places."""
    d = Decimal(str(value))
    sign = "-" if d < 0 else ""
    abs_val = abs(d)
    return f"{sign}${abs_val:,.2f}"


def _format_compact(value) -> str:
    """Format a number compactly: $1.2M, $300K, etc."""
    d = Decimal(str(value))
    sign = "-" if d < 0 else ""
    abs_val = abs(d)
    if abs_val >= 1_000_000:
        return f"{sign}${abs_val / 1_000_000:,.1f}M"
    elif abs_val >= 1_000:
        return f"{sign}${abs_val / 1_000:,.0f}K"
    return f"{sign}${abs_val:,.2f}"


# Register Jinja2 filters
templates.env.filters["format_currency"] = _format_currency
templates.env.filters["format_compact"] = _format_compact


def _load_reference_invoices() -> dict:
    """Load Cinderhaven reference invoice data for reconciliation."""
    ref_path = DATA_DIR / "cinderhaven_reference.json"
    if not ref_path.exists():
        return {}

    with open(ref_path) as f:
        data = json.load(f)

    invoices = {}
    for inv_num, inv_data in data.get("invoices", {}).items():
        invoices[inv_num] = {
            "amount": Decimal(inv_data["amount"]),
            "date": date.fromisoformat(inv_data["date"]),
        }
    return invoices


def _demo_engagement() -> dict:
    """The deployed case study IS the demo engagement — its dispute-window date and
    window length come from engagement.demo.yml (single source of truth), never module
    constants, so the rendered label and the reconciliation math cannot diverge."""
    cfg_path = Path(__file__).parent.parent.parent / "engagement.demo.yml"
    with open(cfg_path) as f:
        return yaml.safe_load(f)


def _scan_stub_filenames() -> list[str]:
    """Return sorted list of all PDF filenames in the stubs directory."""
    if not STUBS_DIR.exists():
        return []
    return sorted(f.name for f in STUBS_DIR.glob("*.pdf"))


def _process_stubs(filenames: list[str]) -> dict:
    """Process a list of stubs and compute aggregate report data.

    Returns a dict with all data needed to render the report template.
    """
    reference_invoices = _load_reference_invoices()

    # Dispute-window date and window come from the demo engagement config (single
    # source), not module constants, so the rendered label and the math cannot diverge.
    # report_date is the reconciliation "as of now"; an old as_of_date-only config
    # falls back to the data window (config, not a constant).
    cfg = _demo_engagement()
    as_of = date.fromisoformat(
        cfg.get("report_date") or cfg.get("data_as_of") or cfg["as_of_date"]
    )
    dispute_window = int(cfg["basis"]["dispute_window_days"])

    stubs_data = []
    all_deductions = []
    category_totals = defaultdict(lambda: {"count": 0, "amount": Decimal("0")})
    total_deduction_amount = Decimal("0")
    verified_count = 0
    flagged_count = 0
    formats_seen = set()

    stubs_dir_resolved = STUBS_DIR.resolve()
    for filename in filenames:
        pdf_path = (STUBS_DIR / filename).resolve()
        if not pdf_path.is_relative_to(stubs_dir_resolved):
            continue
        if not pdf_path.exists() or pdf_path.suffix != ".pdf":
            continue

        # Extract
        extraction_result = extract(pdf_path, skip_llm=True)
        stub = extraction_result.stub

        # Validate
        validation = validate_stub(stub, stub_id=filename)

        # Reconcile as of the config's report date (reconciliation "as of now"),
        # not the live calendar or a module constant.
        reconciliation = reconcile_stub(
            stub,
            reference_invoices,
            dispute_window_days=dispute_window,
            stub_id=filename,
            as_of_date=as_of,
        )

        # Track formats
        formats_seen.add(stub.retailer.value)

        # Track validation counts
        if validation.status == ValidationStatus.VERIFIED:
            verified_count += 1
        else:
            flagged_count += 1

        # Classify deductions by category
        try:
            reason_codes = load_reason_codes(stub.retailer)
        except FileNotFoundError:
            reason_codes = {}

        for deduction in stub.deductions:
            category = DeductionCategory.UNKNOWN
            if deduction.reason_code in reason_codes:
                category = reason_codes[deduction.reason_code].category

            category_totals[category.value]["count"] += 1
            category_totals[category.value]["amount"] += deduction.amount
            total_deduction_amount += deduction.amount

            all_deductions.append({
                "invoice_number": deduction.invoice_number,
                "reason_code": deduction.reason_code,
                "description": deduction.reason_description,
                "amount": deduction.amount,
                "category": category.value,
                "retailer": stub.retailer.value,
            })

        stubs_data.append({
            "filename": filename,
            "stub": stub,
            "validation": validation,
            "reconciliation": reconciliation,
            "extraction_method": extraction_result.method,
        })

    # Sort categories by amount (descending) for chart
    sorted_categories = sorted(
        category_totals.items(),
        key=lambda x: x[1]["amount"],
        reverse=True,
    )

    # Compute recovery potential
    within_window = Decimal("0")
    past_window = Decimal("0")
    for sd in stubs_data:
        recon = sd["reconciliation"]
        if recon.dispute_window_days_remaining is not None:
            if recon.dispute_window_days_remaining > 0:
                within_window += recon.unmatched_amount
            else:
                past_window += recon.unmatched_amount
        else:
            # No date info — assume within window
            within_window += recon.unmatched_amount

    # Total deduction count
    total_deduction_count = len(all_deductions)

    # Recoverable (unreconciled) total: the two dispute-window buckets by
    # construction. The closing section is driven off this so its parts always
    # foot against the stated total (within_window + past_window == this).
    recoverable_total = within_window + past_window

    return {
        "stubs_data": stubs_data,
        "stub_count": len(stubs_data),
        "format_count": len(formats_seen),
        "formats": sorted(formats_seen),
        "total_deduction_count": total_deduction_count,
        "total_deduction_amount": total_deduction_amount,
        "verified_count": verified_count,
        "flagged_count": flagged_count,
        "category_totals": dict(category_totals),
        "sorted_categories": sorted_categories,
        "all_deductions": all_deductions,
        "within_window": within_window,
        "past_window": past_window,
        "recoverable_total": recoverable_total,
        "dispute_window_days": dispute_window,
        "annual_trade_spend": ANNUAL_TRADE_SPEND,
        "total_chargebacks": TOTAL_CHARGEBACKS,
    }


@router.get("", response_class=HTMLResponse)
async def report_page(
    request: Request,
    stubs: Optional[str] = Query(
        default=None,
        description="Comma-separated list of stub filenames to include.",
    ),
    show_all: bool = Query(
        default=True,
        description="If true, include all stubs in the report.",
    ),
):
    """Render the case study report as an HTML page.

    If neither stubs nor show_all is provided, shows a stub
    selection form. Otherwise, processes the requested stubs
    and renders the full report.
    """
    if not stubs and not show_all:
        # Show the stub selection form
        all_filenames = _scan_stub_filenames()
        return templates.TemplateResponse(
            request,
            "report/case_study.html",
            context={
                "show_selector": True,
                "available_stubs": all_filenames,
            },
        )

    # Determine which stubs to process
    if show_all:
        filenames = _scan_stub_filenames()
    else:
        filenames = [s.strip() for s in stubs.split(",") if s.strip()]

    report_data = await asyncio.to_thread(_process_stubs, filenames)

    return templates.TemplateResponse(
        request,
        "report/case_study.html",
        context={
            "show_selector": False,
            "show_all": show_all,
            "selected_stubs": filenames,
            **report_data,
        },
    )


@router.get("/pdf")
async def report_pdf(
    request: Request,
    stubs: Optional[str] = Query(default=None),
    show_all: bool = Query(default=False),
):
    """Generate and return the case study report as a downloadable PDF.

    Uses WeasyPrint to render the same template to PDF. If WeasyPrint
    is unavailable (missing system deps), returns a clear error message.
    """
    # Determine which stubs to process
    if show_all:
        filenames = _scan_stub_filenames()
    elif stubs:
        filenames = [s.strip() for s in stubs.split(",") if s.strip()]
    else:
        return Response(
            content="No stubs specified. Use ?show_all=true or ?stubs=file1.pdf,file2.pdf",
            status_code=400,
            media_type="text/plain",
        )

    report_data = await asyncio.to_thread(_process_stubs, filenames)

    # Render the standalone PDF template (no base.html dependency)
    template = templates.get_template("report/case_study_pdf.html")
    html_content = template.render(
        request=request,
        show_all=show_all,
        selected_stubs=filenames,
        **report_data,
    )

    try:
        from weasyprint import HTML
        from weasyprint import default_url_fetcher

        static_dir = Path(__file__).parent.parent / "static"
        static_prefix = static_dir.resolve().as_uri()

        def _restricted_fetcher(url):
            if url.startswith(static_prefix) or url.startswith("data:"):
                return default_url_fetcher(url)
            return {"string": "", "mime_type": "text/plain"}

        pdf_bytes = HTML(
            string=html_content,
            base_url=str(static_dir),
            url_fetcher=_restricted_fetcher,
        ).write_pdf()

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": "attachment; filename=cinderhaven-case-study.pdf",
            },
        )

    except ImportError:
        return Response(
            content=(
                "WeasyPrint is not installed. PDF generation requires "
                "WeasyPrint with system dependencies (pango, cairo). "
                "Install with: pip install weasyprint. "
                "On Windows, the Docker deployment includes all required "
                "system libraries. The HTML report at /report?show_all=true "
                "is available as an alternative."
            ),
            status_code=503,
            media_type="text/plain",
        )

    except Exception:
        logger.exception("PDF generation failed")
        return Response(
            content=(
                "PDF generation failed due to an internal error. "
                "This is often caused by missing system libraries (pango, cairo). "
                "The HTML report at /report?show_all=true is available as an alternative."
            ),
            status_code=503,
            media_type="text/plain",
        )
