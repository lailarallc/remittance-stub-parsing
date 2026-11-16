"""Tests for U7 interactive demo routes: tour, explore, and review queue.

Covers the guided tour, free exploration, review queue listing,
review detail with PDF viewer, and revalidation endpoint.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.routes.review import _processed_stubs


# --- helpers ---


@pytest_asyncio.fixture
async def client():
    """Async HTTP client bound to the test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
def clear_processed_cache():
    """Clear the in-memory processed stubs cache between tests."""
    _processed_stubs.clear()
    yield
    _processed_stubs.clear()


# --- guided tour ---


@pytest.mark.asyncio
async def test_tour_page_returns_200(client):
    response = await client.get("/tour")
    assert response.status_code == 200
    assert "Guided Tour" in response.text


@pytest.mark.asyncio
async def test_tour_page_has_step_indicators(client):
    response = await client.get("/tour")
    assert response.status_code == 200
    assert "National mass retailer" in response.text
    assert "Club retailer" in response.text
    assert "Distributor A" in response.text
    assert "Distributor B" in response.text


@pytest.mark.asyncio
async def test_tour_step_returns_partial_when_valid(client):
    response = await client.get("/tour/step/1")
    assert response.status_code == 200
    assert "step-result-container" in response.text


@pytest.mark.asyncio
async def test_tour_step_returns_404_when_out_of_range(client):
    response = await client.get("/tour/step/99")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_tour_step_result_returns_stub_card(client):
    response = await client.get("/tour/step/1/result")
    assert response.status_code == 200
    assert "stub-card" in response.text
    assert "Gross Invoice" in response.text


@pytest.mark.asyncio
async def test_tour_broken_step_returns_flagged(client):
    """Step 5 is the broken national mass retailer stub -- should show flagged status."""
    response = await client.get("/tour/step/5/result")
    assert response.status_code == 200
    assert "status-flagged" in response.text


# --- free exploration ---


@pytest.mark.asyncio
async def test_explore_page_returns_200_with_stub_list(client):
    response = await client.get("/explore")
    assert response.status_code == 200
    assert "Free Exploration" in response.text
    # Should have retailer groups
    assert "National mass retailer" in response.text
    assert "Club retailer" in response.text


@pytest.mark.asyncio
async def test_explore_page_has_stub_cards(client):
    response = await client.get("/explore")
    assert response.status_code == 200
    assert "explore-card" in response.text


@pytest.mark.asyncio
async def test_explore_page_marks_broken_stubs(client):
    response = await client.get("/explore")
    assert response.status_code == 200
    assert "explore-card-broken" in response.text
    assert "Broken" in response.text


# --- review queue ---


@pytest.mark.asyncio
async def test_review_queue_returns_200(client):
    response = await client.get("/review")
    assert response.status_code == 200
    assert "Review Queue" in response.text


@pytest.mark.asyncio
async def test_review_queue_lists_flagged_stubs(client):
    response = await client.get("/review")
    assert response.status_code == 200
    # The broken stubs should appear as flagged
    assert "FLAGGED" in response.text


@pytest.mark.asyncio
async def test_review_detail_shows_flagged_stub(client):
    response = await client.get("/review/mass_retailer_stub_broken_arithmetic.pdf")
    assert response.status_code == 200
    # Should have the split layout with PDF viewer and form
    assert "split-layout" in response.text
    assert "pdf-viewer" in response.text
    assert "review-form" in response.text


@pytest.mark.asyncio
async def test_review_detail_returns_404_when_missing(client):
    response = await client.get("/review/nonexistent.pdf")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_review_form_shows_editable_fields(client):
    response = await client.get("/review/mass_retailer_stub_broken_arithmetic.pdf")
    assert response.status_code == 200
    assert "gross_invoice" in response.text
    assert "net_cash" in response.text
    assert "Re-validate" in response.text


# --- revalidation ---


@pytest.mark.asyncio
async def test_revalidate_returns_updated_result(client):
    # First, access the detail page to populate the cache
    detail_resp = await client.get("/review/mass_retailer_stub_broken_arithmetic.pdf")
    assert detail_resp.status_code == 200

    # Submit the form with original values (should still be flagged)
    from app.routes.review import _processed_stubs
    cached = _processed_stubs["mass_retailer_stub_broken_arithmetic.pdf"]
    stub = cached["stub"]

    form_data = {
        "gross_invoice": str(stub.gross_invoice),
        "net_cash": str(stub.net_cash),
    }
    for i, d in enumerate(stub.deductions):
        form_data[f"deduction_{i}_invoice"] = d.invoice_number
        form_data[f"deduction_{i}_reason_code"] = d.reason_code
        form_data[f"deduction_{i}_description"] = d.reason_description
        form_data[f"deduction_{i}_amount"] = str(d.amount)

    response = await client.post(
        "/review/mass_retailer_stub_broken_arithmetic.pdf/revalidate",
        data=form_data,
    )
    assert response.status_code == 200
    assert "review-form" in response.text


@pytest.mark.asyncio
async def test_revalidate_returns_404_when_stub_missing(client):
    response = await client.post(
        "/review/nonexistent.pdf/revalidate",
        data={"gross_invoice": "100", "net_cash": "50"},
    )
    assert response.status_code == 404


# --- PDF serving ---


@pytest.mark.asyncio
async def test_pdf_serving_returns_valid_pdf(client):
    response = await client.get("/stubs/pdf/mass_retailer_stub_01.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    # PDF files start with %PDF
    assert response.content[:5] == b"%PDF-"


@pytest.mark.asyncio
async def test_pdf_serving_returns_404_when_missing(client):
    response = await client.get("/stubs/pdf/nonexistent.pdf")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_pdf_serving_returns_404_for_non_pdf(client):
    response = await client.get("/stubs/pdf/not_a_pdf.txt")
    assert response.status_code == 404
