"""Tests for PDF extraction engine.

Covers format detection, header parsing, amount parsing, deduction extraction,
totals extraction, multi-page handling, and round-trip integration for all
four retailer formats.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.extraction.pdf_extractor import (
    detect_format,
    extract_deductions,
    extract_header,
    extract_stub,
    extract_totals,
    load_format_config,
    parse_amount,
)
from src.models import RetailerFormat


STUBS_DIR = Path(__file__).parent.parent / "stubs"


# --- Amount parsing ---


class TestParseAmount:
    def test_parses_plain_dollar_amount(self):
        assert parse_amount("$1,234.56") == Decimal("1234.56")

    def test_parses_parenthesized_negative_as_positive(self):
        """Parenthesized amounts are deductions -- stored positive in our model."""
        assert parse_amount("($1,234.56)") == Decimal("1234.56")

    def test_parses_amount_without_dollar_sign(self):
        assert parse_amount("1,234.56") == Decimal("1234.56")

    def test_parses_amount_without_commas(self):
        assert parse_amount("$1234.56") == Decimal("1234.56")

    def test_parses_small_amount(self):
        assert parse_amount("$0.99") == Decimal("0.99")

    def test_parses_large_amount(self):
        assert parse_amount("$123,456.78") == Decimal("123456.78")

    def test_raises_on_empty_string(self):
        with pytest.raises(ValueError, match="Empty amount"):
            parse_amount("")

    def test_raises_on_non_numeric(self):
        with pytest.raises(ValueError, match="Cannot parse"):
            parse_amount("abc")


# --- Format detection ---


class TestDetectFormat:
    def test_detects_walmart_format(self):
        assert detect_format(STUBS_DIR / "mass_retailer_stub_01.pdf") == RetailerFormat.WALMART

    def test_detects_costco_format(self):
        assert detect_format(STUBS_DIR / "club_retailer_stub_01.pdf") == RetailerFormat.COSTCO

    def test_detects_unfi_format(self):
        assert detect_format(STUBS_DIR / "distributor_a_stub_01.pdf") == RetailerFormat.UNFI

    def test_detects_kehe_format(self):
        assert detect_format(STUBS_DIR / "distributor_b_stub_01.pdf") == RetailerFormat.KEHE

    def test_raises_on_nonexistent_file(self):
        with pytest.raises(FileNotFoundError):
            detect_format(Path("nonexistent.pdf"))

    def test_raises_on_non_pdf_file(self):
        """Non-PDF file extension raises a clear error."""
        # Use an existing non-PDF file
        non_pdf = Path(__file__)  # this test file itself
        with pytest.raises(ValueError, match="Not a PDF"):
            detect_format(non_pdf)


# --- Header extraction ---


class TestExtractHeader:
    def test_extracts_walmart_header(self):
        stub = extract_stub(STUBS_DIR / "mass_retailer_stub_01.pdf")
        assert stub.check_number == "55176955"
        assert stub.payment_date == date(2024, 6, 13)
        assert stub.payer_name == "National Mass Retailer"

    def test_extracts_costco_header(self):
        stub = extract_stub(STUBS_DIR / "club_retailer_stub_01.pdf")
        assert stub.check_number == "55176955"
        assert stub.payment_date == date(2024, 6, 13)
        assert stub.payer_name == "Club Retailer"

    def test_extracts_unfi_header(self):
        stub = extract_stub(STUBS_DIR / "distributor_a_stub_01.pdf")
        assert stub.check_number == "55176955"
        assert stub.payment_date == date(2024, 6, 13)
        assert stub.payer_name == "Distributor A"

    def test_extracts_kehe_header(self):
        stub = extract_stub(STUBS_DIR / "distributor_b_stub_01.pdf")
        assert stub.check_number == "55176955"
        assert stub.payment_date == date(2024, 6, 13)
        assert stub.payer_name == "Distributor B"


# --- Totals extraction ---


class TestExtractTotals:
    def test_extracts_walmart_totals(self):
        stub = extract_stub(STUBS_DIR / "mass_retailer_stub_01.pdf")
        assert stub.gross_invoice == Decimal("18440.23")
        assert stub.net_cash == Decimal("8109.59")

    def test_extracts_costco_totals(self):
        stub = extract_stub(STUBS_DIR / "club_retailer_stub_01.pdf")
        assert stub.gross_invoice == Decimal("18440.23")
        assert stub.net_cash == Decimal("8109.59")

    def test_extracts_unfi_totals(self):
        stub = extract_stub(STUBS_DIR / "distributor_a_stub_01.pdf")
        assert stub.gross_invoice == Decimal("18440.23")
        assert stub.net_cash == Decimal("8109.59")

    def test_extracts_kehe_totals(self):
        stub = extract_stub(STUBS_DIR / "distributor_b_stub_01.pdf")
        assert stub.gross_invoice == Decimal("18440.23")
        assert stub.net_cash == Decimal("8109.59")

    def test_totals_sum_correct_when_stub_is_clean(self):
        """For a clean stub, gross - net = sum of deduction amounts."""
        stub = extract_stub(STUBS_DIR / "mass_retailer_stub_01.pdf")
        total_deductions = sum(d.amount for d in stub.deductions)
        assert stub.gross_invoice - stub.net_cash == total_deductions


# --- Walmart extraction ---


class TestWalmartExtraction:
    def test_extracts_all_line_items(self):
        stub = extract_stub(STUBS_DIR / "mass_retailer_stub_01.pdf")
        assert len(stub.deductions) == 8

    def test_extracts_correct_reason_codes(self):
        stub = extract_stub(STUBS_DIR / "mass_retailer_stub_01.pdf")
        codes = [d.reason_code for d in stub.deductions]
        assert "24" in codes
        assert "41" in codes
        assert "86" in codes
        assert "22" in codes

    def test_extracts_correct_amounts(self):
        stub = extract_stub(STUBS_DIR / "mass_retailer_stub_01.pdf")
        amounts = {d.invoice_number: d.amount for d in stub.deductions}
        assert amounts["WM-388389"] == Decimal("165.54")
        assert amounts["WM-207473"] == Decimal("557.22")
        assert amounts["WM-106814"] == Decimal("2848.25")

    def test_extracts_invoice_numbers(self):
        stub = extract_stub(STUBS_DIR / "mass_retailer_stub_01.pdf")
        invoices = [d.invoice_number for d in stub.deductions]
        assert "WM-388389" in invoices
        assert "WM-207473" in invoices

    def test_extracts_descriptions(self):
        stub = extract_stub(STUBS_DIR / "mass_retailer_stub_01.pdf")
        descriptions = [d.reason_description for d in stub.deductions]
        assert any("Quality rejection" in d for d in descriptions)
        assert any("Advertising allowance" in d for d in descriptions)


# --- Costco extraction ---


class TestCostcoExtraction:
    def test_extracts_all_line_items(self):
        stub = extract_stub(STUBS_DIR / "club_retailer_stub_01.pdf")
        assert len(stub.deductions) == 8

    def test_extracts_parenthesized_amounts_as_positive(self):
        """Costco uses ($X.XX) format -- should be stored as positive."""
        stub = extract_stub(STUBS_DIR / "club_retailer_stub_01.pdf")
        for d in stub.deductions:
            assert d.amount > 0

    def test_extracts_correct_amounts_from_deduction_column(self):
        """Costco has both Inv Amount and Deduction columns; we use Deduction."""
        stub = extract_stub(STUBS_DIR / "club_retailer_stub_01.pdf")
        total_deductions = sum(d.amount for d in stub.deductions)
        assert total_deductions == stub.gross_invoice - stub.net_cash

    def test_extracts_alpha_reason_codes(self):
        stub = extract_stub(STUBS_DIR / "club_retailer_stub_01.pdf")
        codes = [d.reason_code for d in stub.deductions]
        assert "DM" in codes
        assert "MK" in codes
        assert "SH" in codes


# --- UNFI extraction ---


class TestUnfiExtraction:
    def test_extracts_all_line_items(self):
        stub = extract_stub(STUBS_DIR / "distributor_a_stub_01.pdf")
        assert len(stub.deductions) == 8

    def test_uses_total_column_not_unit_price(self):
        """UNFI has Qty, Unit $, and Total columns; we use Total."""
        stub = extract_stub(STUBS_DIR / "distributor_a_stub_01.pdf")
        total_deductions = sum(d.amount for d in stub.deductions)
        assert total_deductions == stub.gross_invoice - stub.net_cash

    def test_extracts_three_letter_codes(self):
        stub = extract_stub(STUBS_DIR / "distributor_a_stub_01.pdf")
        codes = [d.reason_code for d in stub.deductions]
        assert "OSD" in codes
        assert "VOL" in codes
        assert "MCB" in codes


# --- KeHE extraction ---


class TestKeheExtraction:
    def test_extracts_all_line_items(self):
        stub = extract_stub(STUBS_DIR / "distributor_b_stub_01.pdf")
        assert len(stub.deductions) == 8

    def test_extracts_correct_amounts(self):
        stub = extract_stub(STUBS_DIR / "distributor_b_stub_01.pdf")
        total_deductions = sum(d.amount for d in stub.deductions)
        assert total_deductions == stub.gross_invoice - stub.net_cash

    def test_extracts_kehe_reason_codes(self):
        stub = extract_stub(STUBS_DIR / "distributor_b_stub_01.pdf")
        codes = [d.reason_code for d in stub.deductions]
        assert "PRO" in codes
        assert "DMG" in codes
        assert "MKD" in codes


# --- Multi-page handling ---


class TestMultiPageExtraction:
    def test_extracts_tables_across_page_boundaries(self):
        """UNFI multi-page stub should combine tables from all pages."""
        stub = extract_stub(STUBS_DIR / "distributor_a_stub_multipage.pdf")
        # Generator creates 40-55 line items for multi-page stubs
        assert len(stub.deductions) >= 40

    def test_multipage_amounts_balance(self):
        """Sum of extracted deductions should match gross - net."""
        stub = extract_stub(STUBS_DIR / "distributor_a_stub_multipage.pdf")
        total_deductions = sum(d.amount for d in stub.deductions)
        expected = stub.gross_invoice - stub.net_cash
        assert total_deductions == expected, (
            f"Deduction sum {total_deductions} != gross-net {expected}"
        )

    def test_multipage_skips_repeated_headers(self):
        """Header rows on subsequent pages should not appear as deductions."""
        stub = extract_stub(STUBS_DIR / "distributor_a_stub_multipage.pdf")
        for d in stub.deductions:
            assert d.invoice_number != "Invoice #", (
                "Header row leaked into deductions"
            )
            assert d.reason_code != "Code", (
                "Header row leaked into deductions"
            )


# --- Error handling ---


class TestErrorHandling:
    def test_raises_on_non_pdf_file(self):
        """Attempting to extract a non-PDF file raises a clear error."""
        with pytest.raises(ValueError, match="Not a PDF"):
            extract_stub(Path(__file__))

    def test_raises_on_missing_file(self):
        with pytest.raises(FileNotFoundError):
            extract_stub(Path("does_not_exist.pdf"))


# --- Round-trip integration ---


class TestRoundTrip:
    """Generate a stub, extract it, verify extracted amounts match generator's amounts."""

    def test_walmart_round_trip(self, tmp_path: Path):
        from src.stub_generator.walmart import WalmartStubGenerator

        gen = WalmartStubGenerator(seed=99)
        output_path = tmp_path / "walmart_rt.pdf"
        original = gen.build_clean_stub(output_path)
        gen.write_stub_pdf(original, output_path)

        extracted = extract_stub(output_path)
        assert extracted.retailer == RetailerFormat.WALMART
        assert extracted.check_number == original.check_number
        assert extracted.payment_date == original.payment_date
        assert extracted.gross_invoice == original.gross_invoice
        assert extracted.net_cash == original.net_cash
        assert len(extracted.deductions) == len(original.deductions)

        original_total = sum(d.amount for d in original.deductions)
        extracted_total = sum(d.amount for d in extracted.deductions)
        assert original_total == extracted_total

    def test_costco_round_trip(self, tmp_path: Path):
        from src.stub_generator.costco import CostcoStubGenerator

        gen = CostcoStubGenerator(seed=99)
        output_path = tmp_path / "costco_rt.pdf"
        original = gen.build_clean_stub(output_path)
        gen.write_stub_pdf(original, output_path)

        extracted = extract_stub(output_path)
        assert extracted.retailer == RetailerFormat.COSTCO
        assert extracted.gross_invoice == original.gross_invoice
        assert extracted.net_cash == original.net_cash
        assert len(extracted.deductions) == len(original.deductions)

        original_total = sum(d.amount for d in original.deductions)
        extracted_total = sum(d.amount for d in extracted.deductions)
        assert original_total == extracted_total

    def test_unfi_round_trip(self, tmp_path: Path):
        from src.stub_generator.unfi import UnfiStubGenerator

        gen = UnfiStubGenerator(seed=99)
        output_path = tmp_path / "unfi_rt.pdf"
        original = gen.build_clean_stub(output_path)
        gen.write_stub_pdf(original, output_path)

        extracted = extract_stub(output_path)
        assert extracted.retailer == RetailerFormat.UNFI
        assert extracted.gross_invoice == original.gross_invoice
        assert extracted.net_cash == original.net_cash
        assert len(extracted.deductions) == len(original.deductions)

        original_total = sum(d.amount for d in original.deductions)
        extracted_total = sum(d.amount for d in extracted.deductions)
        assert original_total == extracted_total

    def test_kehe_round_trip(self, tmp_path: Path):
        from src.stub_generator.keHE import KeheStubGenerator

        gen = KeheStubGenerator(seed=99)
        output_path = tmp_path / "kehe_rt.pdf"
        original = gen.build_clean_stub(output_path)
        gen.write_stub_pdf(original, output_path)

        extracted = extract_stub(output_path)
        assert extracted.retailer == RetailerFormat.KEHE
        assert extracted.gross_invoice == original.gross_invoice
        assert extracted.net_cash == original.net_cash
        assert len(extracted.deductions) == len(original.deductions)

        original_total = sum(d.amount for d in original.deductions)
        extracted_total = sum(d.amount for d in extracted.deductions)
        assert original_total == extracted_total
