"""Demo golden lock — remittance-stub-parsing.

The demo output is computed LIVE at request time (app/routes/report.py::
_process_stubs) from the 15 demo stub PDFs + the committed reference ledger +
per-format config. The stub PDFs are gitignored and regenerated deterministically
(seed 42) at Docker build, so there is no committed rendered artifact to byte-lock.

This golden regenerates the demo stubs (seed 42) and runs the real compute path,
asserting the exact aggregate figures the deployed case study renders — including
the ledger-foots invariant the 07-31 audit cared about (recoverable == within +
past by construction). If any figure moves, STOP: a golden moved.
"""

from __future__ import annotations

import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

import app.routes.report as report
from src.stub_generator import generate_all_stubs


@pytest.fixture(scope="module")
def demo_report():
    """Generate seed-42 stubs and run the live compute path against them."""
    tmp = Path(tempfile.mkdtemp()) / "stubs"
    tmp.mkdir(parents=True)
    generate_all_stubs(tmp)
    original = report.STUBS_DIR
    report.STUBS_DIR = tmp
    try:
        names = sorted(p.name for p in tmp.glob("*.pdf"))
        yield report._process_stubs(names)
    finally:
        report.STUBS_DIR = original


def test_stub_and_format_counts(demo_report):
    assert demo_report["stub_count"] == 15
    assert demo_report["format_count"] == 4
    assert demo_report["formats"] == ["costco", "keHE", "unfi", "walmart"]


def test_deduction_count_and_amount(demo_report):
    assert demo_report["total_deduction_count"] == 155
    assert demo_report["total_deduction_amount"] == Decimal("207835.06")


def test_recoverable_total_and_foots(demo_report):
    # The headline recoverable figure, and the invariant the audit cared about:
    # the two dispute-window buckets always foot to the stated total.
    assert demo_report["recoverable_total"] == Decimal("207338.44")
    assert demo_report["within_window"] == Decimal("26173.80")
    assert demo_report["past_window"] == Decimal("181164.64")
    assert (demo_report["within_window"] + demo_report["past_window"]
            == demo_report["recoverable_total"])


def test_validation_counts(demo_report):
    assert demo_report["verified_count"] == 13
    assert demo_report["flagged_count"] == 2
    assert demo_report["verified_count"] + demo_report["flagged_count"] == demo_report["stub_count"]
