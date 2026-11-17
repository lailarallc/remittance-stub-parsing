"""Guided tour routes: tour page, step endpoints, and SSE streaming."""

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse

from src.extraction.pipeline import extract
from src.extraction.pdf_extractor import extract_stub
from src.validation.reason_codes import validate_stub

router = APIRouter(prefix="/tour")

STUBS_DIR = Path(__file__).parent.parent.parent / "stubs"
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Tour steps: one per retailer, plus a broken stub to demonstrate flagging.
TOUR_STEPS = [
    {
        "step": 1,
        "retailer": "National mass retailer",
        "filename": "mass_retailer_stub_01.pdf",
        "description": "Table-heavy layout with promotional allowances, freight claims, and compliance fines. 9 reason codes mapped across 5 deduction categories.",
    },
    {
        "step": 2,
        "retailer": "Club retailer",
        "filename": "club_retailer_stub_01.pdf",
        "description": "Structured two-column layout with volume rebates and warehouse handling deductions. Gross/net reconciliation with multi-line items.",
    },
    {
        "step": 3,
        "retailer": "Distributor A",
        "filename": "distributor_a_stub_01.pdf",
        "description": "Distributor chargebacks for spoilage, short-ships, and invoice discrepancies. Variable-length line items that sometimes span multiple pages.",
    },
    {
        "step": 4,
        "retailer": "Distributor B",
        "filename": "distributor_b_stub_01.pdf",
        "description": "Promotional billbacks, new-item slotting fees, and reclamation deductions. Compact single-page format with merged header rows.",
    },
    {
        "step": 5,
        "retailer": "National mass retailer (broken)",
        "filename": "mass_retailer_stub_broken_arithmetic.pdf",
        "description": "Deliberately broken stub with arithmetic that does not balance. Demonstrates how the validation pipeline flags errors and routes stubs to the review queue.",
    },
]


def _safe_stub_path(filename: str) -> Path:
    """Resolve a stub filename and verify it stays within STUBS_DIR."""
    from fastapi import HTTPException as _HTTPException

    pdf_path = (STUBS_DIR / filename).resolve()
    if not pdf_path.is_relative_to(STUBS_DIR.resolve()):
        raise _HTTPException(status_code=400, detail="Invalid filename")
    if not pdf_path.exists() or pdf_path.suffix != ".pdf":
        raise _HTTPException(status_code=404, detail=f"Stub not found: {filename}")
    return pdf_path


async def _stream_pipeline(stub_filename: str):
    """Generator that yields SSE events as the pipeline runs.

    Each event has a named type and JSON data payload. The actual
    extraction work is synchronous (pdfplumber), so we run it in
    a thread to avoid blocking the event loop.
    """
    pdf_path = _safe_stub_path(stub_filename)

    # Event: extraction started
    yield {
        "event": "extraction_started",
        "data": json.dumps({
            "message": f"Starting extraction for {stub_filename}",
            "filename": stub_filename,
        }),
    }
    await asyncio.sleep(0.3)

    # Event: tables found (run pdfplumber in thread)
    stub = await asyncio.to_thread(extract_stub, pdf_path)
    deduction_count = len(stub.deductions)
    yield {
        "event": "tables_found",
        "data": json.dumps({
            "message": f"Found {deduction_count} deduction line items",
            "deduction_count": deduction_count,
            "retailer": stub.retailer.value,
        }),
    }
    await asyncio.sleep(0.3)

    # Event: validation running
    yield {
        "event": "validation_running",
        "data": json.dumps({
            "message": "Running arithmetic and reason-code validation",
        }),
    }
    await asyncio.sleep(0.2)

    # Run validation
    validation = validate_stub(stub, stub_id=stub_filename)

    # Event: result ready
    yield {
        "event": "result_ready",
        "data": json.dumps({
            "message": "Pipeline complete",
            "filename": stub_filename,
            "retailer": stub.retailer.value,
            "check_number": stub.check_number,
            "gross_invoice": str(stub.gross_invoice),
            "net_cash": str(stub.net_cash),
            "deduction_count": deduction_count,
            "status": validation.status.value,
            "arithmetic_valid": validation.arithmetic_valid,
            "all_codes_mapped": validation.all_codes_mapped,
            "discrepancy_amount": str(validation.discrepancy_amount) if validation.discrepancy_amount else None,
            "issue_count": len(validation.details),
        }),
    }


@router.get("", response_class=HTMLResponse)
async def tour_page(request: Request):
    """Guided tour page with step indicator and progressive walkthrough."""
    return templates.TemplateResponse(
        request,
        "tour.html",
        context={
            "steps": TOUR_STEPS,
            "total_steps": len(TOUR_STEPS),
        },
    )


@router.get("/step/{step_number}", response_class=HTMLResponse)
async def tour_step(step_number: int, request: Request):
    """Return HTMX partial for a specific tour step.

    Renders the step content area with SSE connection info so the
    frontend can stream the pipeline for this step's stub.
    """
    if step_number < 1 or step_number > len(TOUR_STEPS):
        raise HTTPException(status_code=404, detail=f"Invalid step: {step_number}")

    step = TOUR_STEPS[step_number - 1]

    return templates.TemplateResponse(
        request,
        "partials/step_result.html",
        context={
            "step": step,
            "step_number": step_number,
            "total_steps": len(TOUR_STEPS),
            "is_last": step_number == len(TOUR_STEPS),
        },
    )


@router.get("/step/{step_number}/result", response_class=HTMLResponse)
async def tour_step_result(step_number: int, request: Request):
    """Process the stub for a tour step and return the result partial.

    Called after SSE streaming completes to get the full rendered result.
    """
    if step_number < 1 or step_number > len(TOUR_STEPS):
        raise HTTPException(status_code=404, detail=f"Invalid step: {step_number}")

    step = TOUR_STEPS[step_number - 1]
    pdf_path = _safe_stub_path(step["filename"])

    extraction_result = await asyncio.to_thread(extract, pdf_path, skip_llm=True)
    validation = validate_stub(extraction_result.stub, stub_id=step["filename"])

    return templates.TemplateResponse(
        request,
        "partials/stub_card.html",
        context={
            "stub": extraction_result.stub,
            "validation": validation,
            "extraction_method": extraction_result.method,
            "filename": step["filename"],
        },
    )


@router.get("/stream/{stub_filename}")
async def stream_pipeline(stub_filename: str):
    """SSE endpoint that streams extraction + validation progress.

    Connect via HTMX's SSE extension or plain EventSource.
    Events: extraction_started, tables_found, validation_running,
    result_ready.
    """
    _safe_stub_path(stub_filename)

    return EventSourceResponse(_stream_pipeline(stub_filename))
