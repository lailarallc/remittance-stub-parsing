"""Tests for FastAPI web app routes.

Covers landing page, health check, stub listing, processing,
and HTMX partial rendering.
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


# --- landing page ---

@pytest.mark.asyncio
async def test_landing_page_renders(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert "Remittance Stub Parser" in response.text


@pytest.mark.asyncio
async def test_landing_page_has_format_cards(client):
    response = await client.get("/")
    assert response.status_code == 200
    for retailer in ["National mass retailer", "Club retailer", "Distributor A", "Distributor B"]:
        assert retailer in response.text


@pytest.mark.asyncio
async def test_landing_page_has_action_buttons(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert "Start Guided Tour" in response.text
    assert "Explore Freely" in response.text


# --- health check ---

@pytest.mark.asyncio
async def test_health_check_returns_ok(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


# --- stubs listing ---

@pytest.mark.asyncio
async def test_stubs_endpoint_returns_list(client):
    response = await client.get("/stubs")
    assert response.status_code == 200
    stubs = response.json()
    assert isinstance(stubs, list)
    assert len(stubs) > 0


@pytest.mark.asyncio
async def test_stubs_endpoint_includes_retailer_metadata(client):
    response = await client.get("/stubs")
    stubs = response.json()
    # Every stub should have these keys
    for stub in stubs:
        assert "filename" in stub
        assert "retailer" in stub
        assert "is_broken" in stub
        assert stub["retailer"] in ["National mass retailer", "Club retailer", "Distributor A", "Distributor B", "Unknown"]


@pytest.mark.asyncio
async def test_stubs_endpoint_detects_broken_stubs(client):
    response = await client.get("/stubs")
    stubs = response.json()
    broken = [s for s in stubs if s["is_broken"]]
    # We know at least mass_retailer_stub_broken_arithmetic and
    # club_retailer_stub_broken_unmapped_code exist
    assert len(broken) >= 2


# --- process endpoint ---

@pytest.mark.asyncio
async def test_process_returns_result_for_valid_stub(client):
    response = await client.post("/process/mass_retailer_stub_01.pdf")
    assert response.status_code == 200
    # Should return an HTMX partial with stub card content
    assert "stub-card" in response.text
    assert "Gross Invoice" in response.text


@pytest.mark.asyncio
async def test_process_returns_404_for_missing_stub(client):
    response = await client.post("/process/nonexistent.pdf")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_process_returns_404_for_non_pdf(client):
    response = await client.post("/process/not_a_pdf.txt")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_process_result_includes_validation_status(client):
    response = await client.post("/process/mass_retailer_stub_01.pdf")
    assert response.status_code == 200
    # The partial should contain a status badge (verified or flagged)
    assert "status-verified" in response.text or "status-flagged" in response.text


@pytest.mark.asyncio
async def test_process_broken_stub_shows_issues(client):
    response = await client.post("/process/mass_retailer_stub_broken_arithmetic.pdf")
    assert response.status_code == 200
    # Broken arithmetic stub should show flagged status
    assert "status-flagged" in response.text


# --- SSE stream endpoint ---

@pytest.mark.asyncio
async def test_tour_stream_returns_404_for_missing_stub(client):
    response = await client.get("/tour/stream/nonexistent.pdf")
    assert response.status_code == 404


# --- content checks ---

@pytest.mark.asyncio
async def test_landing_page_has_pipeline_explanation(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert "Extract" in response.text
    assert "Validate" in response.text
    assert "Reconcile" in response.text


@pytest.mark.asyncio
async def test_landing_page_includes_lailara_footer(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert "Lailara LLC" in response.text
    assert "lailarallc.com" in response.text
