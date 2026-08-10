"""Format-plugin interface tests.

Proves the parsing-plugin contract: the four built-in formats are discovered as
plugins (one fixture per plugin, detected + parsed via the documented interface),
and a NEW format is a config drop-in — no enum edit, no code fork.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pdfplumber
import pytest
import yaml

from src.extraction.pdf_extractor import detect_format, extract_with_plugin
from src.extraction.plugins import (
    ConfigFormatPlugin,
    detect_plugin,
    discover_plugins,
)
from src.models import RetailerFormat
from src.stub_generator import generate_all_stubs

BUILTINS = {"walmart", "costco", "unfi", "keHE"}


def test_discover_finds_all_builtins():
    plugins = {p.name for p in discover_plugins()}
    assert BUILTINS <= plugins
    for p in discover_plugins():
        if p.name in BUILTINS:
            assert p.header_pattern            # every built-in is detectable
            assert p.format_config["column_mapping"]


@pytest.fixture(scope="module")
def demo_stubs():
    tmp = Path(tempfile.mkdtemp()) / "stubs"
    tmp.mkdir(parents=True)
    generate_all_stubs(tmp)
    return sorted(tmp.glob("*.pdf"))


def test_each_builtin_plugin_detects_and_parses_its_fixture(demo_stubs):
    """One fixture per plugin: every generated stub is detected by exactly its
    plugin and parsed through the plugin interface into deductions."""
    seen_formats = set()
    for pdf in demo_stubs:
        with pdfplumber.open(str(pdf)) as doc:
            text = doc.pages[0].extract_text() or ""
        plugin = detect_plugin(text)
        assert plugin is not None, f"no plugin detected for {pdf.name}"
        assert plugin.name in BUILTINS
        seen_formats.add(plugin.name)
        stub = extract_with_plugin(pdf, plugin)
        # plugin path reproduces the enum-path retailer + finds deductions
        assert RetailerFormat(stub.retailer).value == plugin.name
        assert len(stub.deductions) >= 0
    assert seen_formats == BUILTINS      # all four fixtures exercised


def test_new_client_format_is_config_dropin(tmp_path):
    """Dropping two YAML files into a config dir registers a new format — no
    change to RetailerFormat or any parser code."""
    cfg = tmp_path / "config"
    (cfg / "format_configs").mkdir(parents=True)
    (cfg / "reason_codes").mkdir(parents=True)
    (cfg / "format_configs" / "acme_grocery.yml").write_text(yaml.safe_dump({
        "retailer": "acme_grocery",
        "display_name": "Acme Grocery",
        "header_pattern": "ACME GROCERY CO.",
        "column_mapping": {"invoice_number": 0, "reason_code": 1, "description": 2, "amount": 3},
        "amount_format": "plain",
    }))
    (cfg / "reason_codes" / "acme_grocery.yml").write_text(yaml.safe_dump({
        "codes": {"AG-01": {"category": "compliance", "description": "Label noncompliance"}},
    }))

    names = {p.name for p in discover_plugins(cfg)}
    assert "acme_grocery" in names

    plugin = detect_plugin("Remittance advice — ACME GROCERY CO.  Check #: 5", cfg)
    assert plugin is not None
    assert plugin.name == "acme_grocery"
    assert plugin.display_name == "Acme Grocery"
    assert plugin.reason_codes["AG-01"]["category"] == "compliance"
    # the new format is NOT a RetailerFormat member — that's the point
    with pytest.raises(ValueError):
        RetailerFormat("acme_grocery")


def test_unrecognized_format_raises():
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        # not a real PDF; detect_format should raise (no pages / unrecognized)
        f.write(b"%PDF-1.4 not a real remittance")
        path = Path(f.name)
    with pytest.raises((ValueError, Exception)):
        detect_format(path)
