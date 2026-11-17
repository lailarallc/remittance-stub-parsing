"""Tests for LLM extraction and pipeline orchestration.

All tests use mocked Anthropic clients — no real API key required.
Covers: LLM availability detection, tool response parsing,
malformed response handling, pipeline method selection, and
graceful fallback when no API key is set.
"""

import os
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.extraction.llm_extractor import (
    _convert_raw_deductions,
    _parse_tool_response,
    extract_with_llm,
    is_llm_available,
)
from src.extraction.pipeline import ExtractionResult, extract
from src.models import DeductionEntry, RetailerFormat


STUBS_DIR = Path(__file__).parent.parent / "stubs"


# --- Helper: build a mock Claude API response ---


def _make_tool_response(deductions: list[dict]) -> SimpleNamespace:
    """Build a mock Claude API response with a record_deductions tool use block."""
    tool_block = SimpleNamespace(
        type="tool_use",
        name="record_deductions",
        input={"deductions": deductions},
    )
    return SimpleNamespace(content=[tool_block])


def _make_text_response(text: str = "No deductions found.") -> SimpleNamespace:
    """Build a mock Claude API response with only a text block (no tool use)."""
    text_block = SimpleNamespace(type="text", text=text)
    return SimpleNamespace(content=[text_block])


# --- LLM availability ---


class TestIsLlmAvailable:
    def test_returns_true_when_api_key_is_set(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-key"}):
            assert is_llm_available() is True

    def test_returns_false_when_api_key_is_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            assert is_llm_available() is False

    def test_returns_false_when_api_key_is_empty(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            assert is_llm_available() is False

    def test_returns_false_when_api_key_is_whitespace(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "   "}):
            assert is_llm_available() is False


# --- Tool response parsing ---


class TestParseToolResponse:
    def test_parses_valid_tool_response(self):
        response = _make_tool_response([
            {
                "invoice_number": "WM-388389",
                "reason_code": "24",
                "reason_description": "Quality rejection",
                "amount": "165.54",
            },
        ])
        entries = _parse_tool_response(response)
        assert len(entries) == 1
        assert entries[0].invoice_number == "WM-388389"
        assert entries[0].reason_code == "24"
        assert entries[0].amount == Decimal("165.54")

    def test_parses_multiple_deductions(self):
        response = _make_tool_response([
            {
                "invoice_number": "WM-388389",
                "reason_code": "24",
                "reason_description": "Quality rejection",
                "amount": "165.54",
            },
            {
                "invoice_number": "WM-207473",
                "reason_code": "41",
                "reason_description": "Advertising allowance",
                "amount": "557.22",
            },
        ])
        entries = _parse_tool_response(response)
        assert len(entries) == 2
        assert entries[0].amount == Decimal("165.54")
        assert entries[1].amount == Decimal("557.22")

    def test_parses_empty_deductions_array(self):
        response = _make_tool_response([])
        entries = _parse_tool_response(response)
        assert entries == []

    def test_raises_when_no_tool_use_block(self):
        response = _make_text_response("I couldn't find any deductions.")
        with pytest.raises(RuntimeError, match="did not contain a record_deductions"):
            _parse_tool_response(response)

    def test_raises_when_wrong_tool_name(self):
        block = SimpleNamespace(
            type="tool_use",
            name="wrong_tool",
            input={"deductions": []},
        )
        response = SimpleNamespace(content=[block])
        with pytest.raises(RuntimeError, match="did not contain a record_deductions"):
            _parse_tool_response(response)


# --- Raw deduction conversion ---


class TestConvertRawDeductions:
    def test_converts_clean_items(self):
        raw = [
            {
                "invoice_number": "INV-001",
                "reason_code": "24",
                "reason_description": "Some reason",
                "amount": "100.50",
            },
        ]
        entries = _convert_raw_deductions(raw)
        assert len(entries) == 1
        assert entries[0].amount == Decimal("100.50")
        assert entries[0].invoice_number == "INV-001"

    def test_strips_dollar_signs_from_amount(self):
        raw = [
            {
                "invoice_number": "INV-001",
                "reason_code": "24",
                "reason_description": "Test",
                "amount": "$1,234.56",
            },
        ]
        entries = _convert_raw_deductions(raw)
        assert entries[0].amount == Decimal("1234.56")

    def test_converts_negative_amount_to_positive(self):
        raw = [
            {
                "invoice_number": "INV-001",
                "reason_code": "24",
                "reason_description": "Test",
                "amount": "-500.00",
            },
        ]
        entries = _convert_raw_deductions(raw)
        assert entries[0].amount == Decimal("500.00")

    def test_skips_non_numeric_amount(self):
        """Items with unparseable amounts are skipped, not crashed on."""
        raw = [
            {
                "invoice_number": "INV-001",
                "reason_code": "24",
                "reason_description": "Test",
                "amount": "not-a-number",
            },
            {
                "invoice_number": "INV-002",
                "reason_code": "41",
                "reason_description": "Valid",
                "amount": "200.00",
            },
        ]
        entries = _convert_raw_deductions(raw)
        assert len(entries) == 1
        assert entries[0].invoice_number == "INV-002"

    def test_handles_missing_fields_gracefully(self):
        """Items missing optional-ish fields still parse (with defaults)."""
        raw = [
            {
                "amount": "99.99",
            },
        ]
        entries = _convert_raw_deductions(raw)
        assert len(entries) == 1
        assert entries[0].invoice_number == ""
        assert entries[0].reason_code == ""
        assert entries[0].amount == Decimal("99.99")


# --- extract_with_llm ---


class TestExtractWithLlm:
    def test_returns_deductions_from_mocked_client(self):
        """End-to-end with a mocked client — verifies the full call path."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_tool_response([
            {
                "invoice_number": "WM-388389",
                "reason_code": "24",
                "reason_description": "Quality rejection",
                "amount": "165.54",
            },
            {
                "invoice_number": "WM-207473",
                "reason_code": "41",
                "reason_description": "Advertising allowance",
                "amount": "557.22",
            },
        ])

        entries = extract_with_llm("some PDF text here", client=mock_client)
        assert len(entries) == 2
        assert entries[0].invoice_number == "WM-388389"
        assert entries[1].amount == Decimal("557.22")

        # Verify the client was called with correct parameters
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-haiku-4-5-20251001"
        assert call_kwargs["tool_choice"] == {"type": "tool", "name": "record_deductions"}
        assert len(call_kwargs["tools"]) == 1
        assert call_kwargs["tools"][0]["name"] == "record_deductions"

    def test_raises_runtime_error_when_no_key_and_no_client(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError, match="No ANTHROPIC_API_KEY"):
                extract_with_llm("some text")

    def test_raises_runtime_error_when_api_call_fails(self):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API timeout")

        with pytest.raises(RuntimeError, match="Claude API call failed"):
            extract_with_llm("some text", client=mock_client)

    def test_passes_pdf_text_in_user_message(self):
        """Verify the PDF text is included in the message to Claude."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_tool_response([])

        extract_with_llm("NATIONAL MASS RETAILER Check #: 55176955", client=mock_client)

        call_kwargs = mock_client.messages.create.call_args.kwargs
        user_msg = call_kwargs["messages"][0]["content"]
        assert "NATIONAL MASS RETAILER Check #: 55176955" in user_msg


# --- Pipeline ---


class TestPipeline:
    def test_returns_pdfplumber_result_when_llm_skipped(self):
        result = extract(STUBS_DIR / "mass_retailer_stub_01.pdf", skip_llm=True)
        assert isinstance(result, ExtractionResult)
        assert result.method == "pdfplumber"
        assert result.llm_used is False
        assert result.stub.retailer == RetailerFormat.WALMART
        assert len(result.stub.deductions) == 8
        assert result.pdfplumber_count == 8

    def test_returns_pdfplumber_result_when_no_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            result = extract(STUBS_DIR / "mass_retailer_stub_01.pdf")
        assert result.method == "pdfplumber"
        assert result.llm_used is False
        assert any("No ANTHROPIC_API_KEY" in w for w in result.warnings)

    def test_raises_when_force_llm_and_no_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError, match="force_llm=True"):
                extract(STUBS_DIR / "mass_retailer_stub_01.pdf", force_llm=True)

    def test_prefers_llm_when_llm_finds_more_deductions(self):
        """When LLM finds more deductions than pdfplumber, use LLM results."""
        # Build a mock client that returns 10 deductions (pdfplumber finds 8)
        llm_deductions = [
            {
                "invoice_number": f"INV-{i:03d}",
                "reason_code": "24",
                "reason_description": f"Deduction {i}",
                "amount": f"{100 + i * 10}.00",
            }
            for i in range(10)
        ]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_tool_response(llm_deductions)

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}):
            result = extract(
                STUBS_DIR / "mass_retailer_stub_01.pdf",
                client=mock_client,
            )

        assert result.method == "pdfplumber+llm"
        assert result.llm_used is True
        assert result.llm_count == 10
        assert result.pdfplumber_count == 8
        assert len(result.stub.deductions) == 10

    def test_prefers_pdfplumber_when_counts_are_equal(self):
        """When both methods find the same count, keep deterministic pdfplumber."""
        # Build a mock client that returns exactly 8 deductions (same as pdfplumber)
        llm_deductions = [
            {
                "invoice_number": f"LLM-{i:03d}",
                "reason_code": "99",
                "reason_description": f"LLM deduction {i}",
                "amount": f"{200 + i * 10}.00",
            }
            for i in range(8)
        ]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_tool_response(llm_deductions)

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}):
            result = extract(
                STUBS_DIR / "mass_retailer_stub_01.pdf",
                client=mock_client,
            )

        assert result.method == "pdfplumber"
        assert result.llm_used is True
        # Deductions should be pdfplumber's, not LLM's
        assert result.stub.deductions[0].invoice_number != "LLM-000"

    def test_prefers_pdfplumber_when_llm_finds_fewer(self):
        """When LLM finds fewer deductions, keep pdfplumber results."""
        llm_deductions = [
            {
                "invoice_number": "LLM-001",
                "reason_code": "24",
                "reason_description": "Single deduction",
                "amount": "100.00",
            },
        ]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_tool_response(llm_deductions)

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}):
            result = extract(
                STUBS_DIR / "mass_retailer_stub_01.pdf",
                client=mock_client,
            )

        assert result.method == "pdfplumber"
        assert result.llm_used is True
        assert result.pdfplumber_count == 8
        assert result.llm_count == 1
        assert len(result.stub.deductions) == 8
        assert any("fewer" in w for w in result.warnings)

    def test_falls_back_to_pdfplumber_when_llm_errors(self):
        """If LLM call raises an exception, fall back gracefully."""
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API rate limit")

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}):
            result = extract(
                STUBS_DIR / "mass_retailer_stub_01.pdf",
                client=mock_client,
            )

        assert result.method == "pdfplumber"
        assert result.llm_error is not None
        assert "rate limit" in result.llm_error
        assert len(result.stub.deductions) == 8

    def test_preserves_header_fields_when_using_llm_deductions(self):
        """When LLM deductions are preferred, header/totals come from pdfplumber."""
        llm_deductions = [
            {
                "invoice_number": f"INV-{i:03d}",
                "reason_code": "24",
                "reason_description": f"Deduction {i}",
                "amount": f"{100 + i * 10}.00",
            }
            for i in range(10)
        ]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_tool_response(llm_deductions)

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}):
            result = extract(
                STUBS_DIR / "mass_retailer_stub_01.pdf",
                client=mock_client,
            )

        # Header fields should still come from pdfplumber
        assert result.stub.check_number == "55176955"
        assert result.stub.payer_name == "National Mass Retailer"
        assert result.stub.gross_invoice == Decimal("18440.23")
        assert result.stub.net_cash == Decimal("8109.59")
        assert result.stub.retailer == RetailerFormat.WALMART

    def test_costco_pipeline_with_skip_llm(self):
        result = extract(STUBS_DIR / "club_retailer_stub_01.pdf", skip_llm=True)
        assert result.stub.retailer == RetailerFormat.COSTCO
        assert result.pdfplumber_count == 8

    def test_unfi_pipeline_with_skip_llm(self):
        result = extract(STUBS_DIR / "distributor_a_stub_01.pdf", skip_llm=True)
        assert result.stub.retailer == RetailerFormat.UNFI
        assert result.pdfplumber_count == 8

    def test_kehe_pipeline_with_skip_llm(self):
        result = extract(STUBS_DIR / "distributor_b_stub_01.pdf", skip_llm=True)
        assert result.stub.retailer == RetailerFormat.KEHE
        assert result.pdfplumber_count == 8

    def test_extraction_result_dataclass_fields(self):
        """Verify ExtractionResult has all expected fields with correct defaults."""
        result = extract(STUBS_DIR / "mass_retailer_stub_01.pdf", skip_llm=True)
        assert hasattr(result, "stub")
        assert hasattr(result, "method")
        assert hasattr(result, "llm_used")
        assert hasattr(result, "llm_error")
        assert hasattr(result, "pdfplumber_count")
        assert hasattr(result, "llm_count")
        assert hasattr(result, "warnings")
        assert result.llm_error is None
        assert result.llm_count == 0
        assert result.warnings == []
