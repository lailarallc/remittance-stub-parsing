"""No real trading-partner name reaches a page, a stub PDF or a file name.

The demo stubs carry invented Cinderhaven figures, so every surface a reader
sees shows role labels. The internal format keys are not public surfaces.
"""

import re
import tempfile
from pathlib import Path

import pdfplumber
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from src.models import RetailerFormat
from src.stub_generator import generate_all_stubs

REAL = re.compile(r"walmart|costco|unfi|kehe", re.I)


def test_display_names_and_file_slugs_are_role_labels():
    for fmt in RetailerFormat:
        assert not REAL.search(fmt.display_name)
        assert not REAL.search(fmt.file_slug)


def test_generated_stub_pdfs_name_no_real_partner():
    out = Path(tempfile.mkdtemp())
    paths = generate_all_stubs(out)
    assert len(paths) == 15
    for path in out.glob("*.pdf"):
        assert not REAL.search(path.name), path.name
        with pdfplumber.open(path) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        assert not REAL.search(text), path.name


@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["/", "/tour", "/explore", "/review", "/report?show_all=true"])
async def test_pages_name_no_real_partner(url):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(url)
    assert response.status_code == 200
    assert not REAL.search(response.text), sorted(set(REAL.findall(response.text)))
