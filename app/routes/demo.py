"""Demo routes: landing page, stub listing, processing, and exploration."""

import asyncio
import functools
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from src.extraction.pipeline import extract
from src.validation.reason_codes import validate_stub

router = APIRouter()

STUBS_DIR = Path(__file__).parent.parent.parent / "stubs"
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@functools.cache
def _scan_stubs() -> tuple[dict, ...]:
    """Scan the stubs/ directory and return metadata for each PDF.

    Cached because the stubs directory is static at runtime.
    Returns a tuple (hashable) for cache compatibility.
    """
    if not STUBS_DIR.exists():
        return ()

    stubs = []
    for pdf in sorted(STUBS_DIR.glob("*.pdf")):
        name = pdf.stem
        name_lower = name.lower()
        if name_lower.startswith("mass_retailer"):
            retailer = "National mass retailer"
        elif name_lower.startswith("club_retailer"):
            retailer = "Club retailer"
        elif name_lower.startswith("distributor_a"):
            retailer = "Distributor A"
        elif name_lower.startswith("distributor_b"):
            retailer = "Distributor B"
        else:
            retailer = "Unknown"

        is_broken = "broken" in name_lower
        stubs.append({
            "filename": pdf.name,
            "name": name.replace("_", " ").title(),
            "retailer": retailer,
            "is_broken": is_broken,
            "size_kb": round(pdf.stat().st_size / 1024, 1),
        })

    return tuple(stubs)


@router.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    """Render the landing page."""
    return templates.TemplateResponse(request, "index.html")


@router.get("/stubs")
async def list_stubs():
    """Return JSON list of available stubs in the stubs/ directory."""
    return _scan_stubs()


@router.get("/explore", response_class=HTMLResponse)
async def explore_page(request: Request):
    """Free exploration page: pick any stub and run it through the pipeline."""
    stubs = _scan_stubs()

    # Group stubs by retailer for display
    retailers = {}
    for stub in stubs:
        retailer = stub["retailer"]
        if retailer not in retailers:
            retailers[retailer] = []
        retailers[retailer].append(stub)

    return templates.TemplateResponse(
        request,
        "explore.html",
        context={"retailers": retailers},
    )


_MAX_STUB_SIZE = 10 * 1024 * 1024  # 10 MB


def _safe_stub_path(filename: str) -> Path:
    """Resolve a stub filename and verify it stays within STUBS_DIR."""
    pdf_path = (STUBS_DIR / filename).resolve()
    if not pdf_path.is_relative_to(STUBS_DIR.resolve()):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not pdf_path.exists() or pdf_path.suffix != ".pdf":
        raise HTTPException(status_code=404, detail=f"PDF not found: {filename}")
    if pdf_path.stat().st_size > _MAX_STUB_SIZE:
        raise HTTPException(status_code=413, detail="File too large")
    return pdf_path


@router.get("/stubs/pdf/{filename}")
async def serve_pdf(filename: str):
    """Serve a stub PDF file for iframe display in the review queue."""
    pdf_path = _safe_stub_path(filename)
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=filename,
    )


@router.post("/process/{stub_filename}", response_class=HTMLResponse)
async def process_stub(stub_filename: str, request: Request):
    """Run extraction + validation on a stub, return HTMX partial.

    Extracts data from the PDF using the pipeline (pdfplumber,
    optionally LLM), validates arithmetic and reason codes, and
    returns a rendered stub_card partial for HTMX swap.
    """
    pdf_path = _safe_stub_path(stub_filename)

    # Run extraction (skip LLM for demo speed)
    extraction_result = await asyncio.to_thread(extract, pdf_path, skip_llm=True)
    stub = extraction_result.stub

    # Run validation
    validation = validate_stub(stub, stub_id=stub_filename)

    return templates.TemplateResponse(
        request,
        "partials/stub_card.html",
        context={
            "stub": stub,
            "validation": validation,
            "extraction_method": extraction_result.method,
            "filename": stub_filename,
        },
    )
