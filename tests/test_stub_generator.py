"""Tests for synthetic remittance stub generation.

Covers happy-path generation, arithmetic validation, multi-page handling,
broken stubs, and pdfplumber text extraction for all four formats.
"""

from decimal import Decimal
from pathlib import Path

import pdfplumber
import pytest

from src.models import RetailerFormat, load_reason_codes
from src.stub_generator import generate_all_stubs
from src.stub_generator.costco import CostcoStubGenerator
from src.stub_generator.keHE import KeheStubGenerator
from src.stub_generator.unfi import UnfiStubGenerator
from src.stub_generator.walmart import WalmartStubGenerator


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory for generated stubs."""
    return tmp_path / "stubs"


class TestWalmartGeneration:
    def test_generates_valid_pdf_with_extractable_text(self, output_dir: Path):
        gen = WalmartStubGenerator()
        paths = gen.generate(output_dir)

        # At least the 3 clean stubs + 1 broken
        assert len(paths) >= 4

        # First clean stub should be a valid PDF
        with pdfplumber.open(paths[0]) as pdf:
            text = pdf.pages[0].extract_text()
            assert "NATIONAL MASS RETAILER" in text
            assert "PAYMENT ADVICE" in text

    def test_clean_stub_amounts_balance(self, output_dir: Path):
        gen = WalmartStubGenerator()
        stub = gen.build_clean_stub(output_dir / "test.pdf")

        total_deductions = sum(d.amount for d in stub.deductions)
        expected_gross = stub.net_cash + total_deductions

        assert stub.gross_invoice == expected_gross, (
            f"Arithmetic mismatch: gross={stub.gross_invoice}, "
            f"net={stub.net_cash}, deductions={total_deductions}"
        )


class TestCostcoGeneration:
    def test_generates_valid_pdf_with_extractable_text(self, output_dir: Path):
        gen = CostcoStubGenerator()
        paths = gen.generate(output_dir)

        assert len(paths) >= 4

        with pdfplumber.open(paths[0]) as pdf:
            text = pdf.pages[0].extract_text()
            assert "CLUB RETAILER" in text
            assert "REMITTANCE DETAIL" in text

    def test_clean_stub_amounts_balance(self, output_dir: Path):
        gen = CostcoStubGenerator()
        stub = gen.build_clean_stub(output_dir / "test.pdf")

        total_deductions = sum(d.amount for d in stub.deductions)
        expected_gross = stub.net_cash + total_deductions

        assert stub.gross_invoice == expected_gross


class TestUnfiGeneration:
    def test_generates_valid_pdf_with_extractable_text(self, output_dir: Path):
        gen = UnfiStubGenerator()
        paths = gen.generate(output_dir)

        assert len(paths) >= 4

        with pdfplumber.open(paths[0]) as pdf:
            text = pdf.pages[0].extract_text()
            assert "DISTRIBUTOR A" in text
            assert "SETTLEMENT STATEMENT" in text

    def test_clean_stub_amounts_balance(self, output_dir: Path):
        gen = UnfiStubGenerator()
        stub = gen.build_clean_stub(output_dir / "test.pdf")

        total_deductions = sum(d.amount for d in stub.deductions)
        expected_gross = stub.net_cash + total_deductions

        assert stub.gross_invoice == expected_gross

    def test_multipage_stub_generates_correctly(self, output_dir: Path):
        gen = UnfiStubGenerator()
        output_dir.mkdir(parents=True, exist_ok=True)
        multipage_path = output_dir / "multipage.pdf"
        stub = gen.build_multipage_stub(multipage_path)
        gen.write_stub_pdf(stub, multipage_path)

        assert multipage_path.exists()
        assert len(stub.deductions) >= 40

        with pdfplumber.open(multipage_path) as pdf:
            assert len(pdf.pages) >= 2, (
                f"Expected multi-page PDF but got {len(pdf.pages)} page(s) "
                f"with {len(stub.deductions)} line items"
            )

    def test_multipage_stub_amounts_balance(self, output_dir: Path):
        gen = UnfiStubGenerator()
        output_dir.mkdir(parents=True, exist_ok=True)
        stub = gen.build_multipage_stub(output_dir / "test.pdf")

        total_deductions = sum(d.amount for d in stub.deductions)
        expected_gross = stub.net_cash + total_deductions

        assert stub.gross_invoice == expected_gross


class TestKeheGeneration:
    def test_generates_valid_pdf_with_extractable_text(self, output_dir: Path):
        gen = KeheStubGenerator()
        paths = gen.generate(output_dir)

        assert len(paths) >= 3

        with pdfplumber.open(paths[0]) as pdf:
            text = pdf.pages[0].extract_text()
            assert "DISTRIBUTOR B" in text
            assert "REMITTANCE ADVICE" in text

    def test_clean_stub_amounts_balance(self, output_dir: Path):
        gen = KeheStubGenerator()
        stub = gen.build_clean_stub(output_dir / "test.pdf")

        total_deductions = sum(d.amount for d in stub.deductions)
        expected_gross = stub.net_cash + total_deductions

        assert stub.gross_invoice == expected_gross


class TestBrokenStubs:
    def test_walmart_broken_stub_has_arithmetic_mismatch(self, output_dir: Path):
        gen = WalmartStubGenerator()
        output_dir.mkdir(parents=True, exist_ok=True)
        broken_path = output_dir / "broken.pdf"
        stub = gen.build_broken_stub_arithmetic(broken_path)

        total_deductions = sum(d.amount for d in stub.deductions)
        expected_gross = stub.net_cash + total_deductions

        discrepancy = stub.gross_invoice - expected_gross
        assert discrepancy == Decimal("42.50"), (
            f"Expected $42.50 discrepancy, got ${discrepancy}"
        )

    def test_costco_broken_stub_has_unmapped_reason_code(self, output_dir: Path):
        gen = CostcoStubGenerator()
        output_dir.mkdir(parents=True, exist_ok=True)
        broken_path = output_dir / "broken.pdf"
        stub = gen.build_broken_stub_unmapped_code(broken_path)

        codes = load_reason_codes(RetailerFormat.COSTCO)
        unmapped_codes = [
            d.reason_code for d in stub.deductions if d.reason_code not in codes
        ]

        assert len(unmapped_codes) >= 1, "Expected at least one unmapped reason code"
        assert "XX" in unmapped_codes, "Expected unmapped code 'XX'"

    def test_broken_stub_with_unmapped_code_still_balances(self, output_dir: Path):
        gen = CostcoStubGenerator()
        output_dir.mkdir(parents=True, exist_ok=True)
        broken_path = output_dir / "broken.pdf"
        stub = gen.build_broken_stub_unmapped_code(broken_path)

        total_deductions = sum(d.amount for d in stub.deductions)
        expected_gross = stub.net_cash + total_deductions

        assert stub.gross_invoice == expected_gross, (
            "Broken-code stub should still balance arithmetically"
        )


class TestPdfplumberExtraction:
    """Integration tests: pdfplumber can open and extract text from each format."""

    def test_pdfplumber_extracts_walmart_text(self, output_dir: Path):
        gen = WalmartStubGenerator()
        paths = gen.generate(output_dir)

        with pdfplumber.open(paths[0]) as pdf:
            text = pdf.pages[0].extract_text()
            assert text is not None
            assert len(text) > 100  # meaningful content, not empty

    def test_pdfplumber_extracts_costco_text(self, output_dir: Path):
        gen = CostcoStubGenerator()
        paths = gen.generate(output_dir)

        with pdfplumber.open(paths[0]) as pdf:
            text = pdf.pages[0].extract_text()
            assert text is not None
            assert len(text) > 100

    def test_pdfplumber_extracts_unfi_text(self, output_dir: Path):
        gen = UnfiStubGenerator()
        paths = gen.generate(output_dir)

        with pdfplumber.open(paths[0]) as pdf:
            text = pdf.pages[0].extract_text()
            assert text is not None
            assert len(text) > 100

    def test_pdfplumber_extracts_kehe_text(self, output_dir: Path):
        gen = KeheStubGenerator()
        paths = gen.generate(output_dir)

        with pdfplumber.open(paths[0]) as pdf:
            text = pdf.pages[0].extract_text()
            assert text is not None
            assert len(text) > 100


class TestGenerateAll:
    def test_generate_all_stubs_creates_files(self, output_dir: Path):
        paths = generate_all_stubs(output_dir)

        # 3 clean per retailer (4 retailers) + 1 broken walmart + 1 broken costco + 1 multipage UNFI = 16
        assert len(paths) >= 15

        for path in paths:
            assert path.exists(), f"Generated stub not found: {path}"
            assert path.stat().st_size > 0, f"Generated stub is empty: {path}"

    def test_generate_all_stubs_are_valid_pdfs(self, output_dir: Path):
        paths = generate_all_stubs(output_dir)

        for path in paths:
            with pdfplumber.open(path) as pdf:
                assert len(pdf.pages) >= 1, f"PDF has no pages: {path}"
                text = pdf.pages[0].extract_text()
                assert text is not None, f"Could not extract text from: {path}"

    def test_generate_all_is_deterministic(self, output_dir: Path, tmp_path: Path):
        dir_a = output_dir
        dir_b = tmp_path / "stubs_b"

        paths_a = generate_all_stubs(dir_a)
        paths_b = generate_all_stubs(dir_b)

        assert len(paths_a) == len(paths_b)

        for path_a, path_b in zip(paths_a, paths_b):
            size_a = path_a.stat().st_size
            size_b = path_b.stat().st_size
            assert size_a == size_b, (
                f"Non-deterministic output: {path_a.name} "
                f"({size_a} bytes) vs ({size_b} bytes)"
            )
