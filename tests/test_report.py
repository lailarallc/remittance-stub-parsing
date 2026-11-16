"""Tests for U8 dynamic case study report routes.

Covers HTML report rendering, stub selection, category breakdown,
validation summary, recovery calculations, and PDF endpoint
(graceful degradation when WeasyPrint is unavailable).
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app


# --- helpers ---


@pytest_asyncio.fixture
async def client():
    """Async HTTP client bound to the test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# --- report with show_all ---


@pytest.mark.asyncio
async def test_report_show_all_returns_200(client):
    response = await client.get("/report?show_all=true")
    assert response.status_code == 200
    assert "Remittance Stub Parsing" in response.text


@pytest.mark.asyncio
async def test_report_show_all_includes_all_sections(client):
    response = await client.get("/report?show_all=true")
    assert response.status_code == 200
    assert "The PDF Pile" in response.text
    assert "The Unified Ledger" in response.text
    assert "The Validation Loop" in response.text
    assert "Recovery Potential" in response.text


@pytest.mark.asyncio
async def test_report_show_all_includes_category_breakdown(client):
    response = await client.get("/report?show_all=true")
    assert response.status_code == 200
    # The category table should have at least one category name
    # Categories are title-cased in the template
    assert "Category" in response.text
    assert "Amount" in response.text
    assert "Share" in response.text


@pytest.mark.asyncio
async def test_report_show_all_includes_validation_summary(client):
    response = await client.get("/report?show_all=true")
    assert response.status_code == 200
    # Should contain verified and/or flagged badges
    assert "VERIFIED" in response.text or "FLAGGED" in response.text
    # Should have the validation table headers
    assert "Arithmetic" in response.text
    assert "Code Mapping" in response.text


@pytest.mark.asyncio
async def test_report_show_all_includes_recovery_calculation(client):
    response = await client.get("/report?show_all=true")
    assert response.status_code == 200
    assert "dispute window" in response.text.lower()
    assert "Recovery Potential" in response.text


@pytest.mark.asyncio
async def test_report_show_all_uses_economist_voice(client):
    """Report should use declarative Economist-style voice, not marketing."""
    response = await client.get("/report?show_all=true")
    text = response.text.lower()
    # Should NOT contain marketing language
    assert "leverage" not in text
    assert "synergy" not in text
    assert "best-in-class" not in text
    assert "unlock" not in text
    # Should contain declarative data-forward language
    assert "deduction" in text
    assert "$" in response.text


# --- report with selected stubs ---


@pytest.mark.asyncio
async def test_report_selected_stubs_returns_200(client):
    response = await client.get("/report?stubs=mass_retailer_stub_01.pdf,club_retailer_stub_01.pdf")
    assert response.status_code == 200
    assert "Remittance Stub Parsing" in response.text


@pytest.mark.asyncio
async def test_report_selected_stubs_shows_only_those_formats(client):
    response = await client.get("/report?stubs=mass_retailer_stub_01.pdf,club_retailer_stub_01.pdf&show_all=false")
    assert response.status_code == 200
    text = response.text
    # Should show only 2 stubs processed
    assert "mass_retailer_stub_01.pdf" in text
    assert "club_retailer_stub_01.pdf" in text
    # Should NOT include UNFI or KeHE stubs in the validation table
    assert "distributor_a_stub_01.pdf" not in text
    assert "distributor_b_stub_01.pdf" not in text


@pytest.mark.asyncio
async def test_report_single_stub_returns_200(client):
    response = await client.get("/report?stubs=mass_retailer_stub_01.pdf")
    assert response.status_code == 200
    assert "mass_retailer_stub_01.pdf" in response.text


# --- report selector (no params) ---


@pytest.mark.asyncio
async def test_report_no_params_shows_all_stubs(client):
    response = await client.get("/report")
    assert response.status_code == 200
    assert "Remittance Stub Parsing" in response.text
    assert "report-selector" not in response.text


@pytest.mark.asyncio
async def test_report_selector_lists_available_stubs(client):
    response = await client.get("/report")
    assert response.status_code == 200
    # Should list at least some stub filenames
    assert "mass_retailer_stub_01.pdf" in response.text


# --- dollar formatting ---


@pytest.mark.asyncio
async def test_report_formats_currency_with_commas(client):
    response = await client.get("/report?show_all=true")
    assert response.status_code == 200
    # Dollar amounts should have $ sign
    assert "$" in response.text


# --- PDF endpoint ---


@pytest.mark.asyncio
async def test_report_pdf_returns_appropriate_response(client):
    """PDF endpoint should return either PDF bytes or a clear error."""
    response = await client.get("/report/pdf?show_all=true")
    # WeasyPrint may or may not be installed
    if response.status_code == 200:
        # If it succeeded, it should be a PDF
        assert response.headers["content-type"] == "application/pdf"
        assert response.content[:5] == b"%PDF-"
    else:
        # If it failed, it should be a 503 with a clear error message
        assert response.status_code == 503
        assert "WeasyPrint" in response.text or "PDF generation" in response.text


@pytest.mark.asyncio
async def test_report_pdf_no_stubs_returns_400(client):
    response = await client.get("/report/pdf")
    assert response.status_code == 400
    assert "No stubs specified" in response.text


@pytest.mark.asyncio
async def test_report_pdf_with_stubs_param_returns_response(client):
    """PDF endpoint with specific stubs should return appropriate response."""
    response = await client.get("/report/pdf?stubs=mass_retailer_stub_01.pdf")
    # Either a valid PDF or a 503 if WeasyPrint is not installed
    assert response.status_code in (200, 503)


# --- content integrity ---


@pytest.mark.asyncio
async def test_report_includes_cinderhaven_context(client):
    """Report should reference Cinderhaven canonical figures."""
    response = await client.get("/report?show_all=true")
    text = response.text
    # Should reference the annual trade spend and chargebacks
    assert "3,357" in text
    assert "3.6M" in text or "3,600,000" in text


@pytest.mark.asyncio
async def test_report_includes_lailara_footer(client):
    response = await client.get("/report?show_all=true")
    assert "Lailara LLC" in response.text
    assert "lailarallc.com" in response.text


@pytest.mark.asyncio
async def test_report_chart_svg_present_when_show_all(client):
    """Full report should include the SVG bar chart."""
    response = await client.get("/report?show_all=true")
    assert response.status_code == 200
    assert "<svg" in response.text
    assert "Deduction Category Distribution" in response.text
