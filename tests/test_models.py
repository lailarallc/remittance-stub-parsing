from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.models import (
    DeductionCategory,
    DeductionEntry,
    ReasonCode,
    ReconciliationMatch,
    ReconciliationResult,
    RemittanceStub,
    RetailerFormat,
    ValidationDetail,
    ValidationResult,
    ValidationStatus,
    is_reason_code_mapped,
    load_reason_codes,
)


class TestDeductionEntry:
    def test_accepts_valid_financial_data(self):
        entry = DeductionEntry(
            invoice_number="INV-2024-001",
            reason_code="22",
            reason_description="Shortage claim",
            amount=Decimal("150.00"),
            deduction_date=date(2024, 6, 15),
        )
        assert entry.amount == Decimal("150.00")
        assert entry.invoice_number == "INV-2024-001"

    def test_zero_amount_is_valid(self):
        entry = DeductionEntry(
            invoice_number="INV-2024-002",
            reason_code="41",
            reason_description="Informational — no charge",
            amount=Decimal("0"),
        )
        assert entry.amount == Decimal("0")

    def test_negative_amount_is_valid(self):
        entry = DeductionEntry(
            invoice_number="INV-2024-003",
            reason_code="72",
            reason_description="Credit adjustment",
            amount=Decimal("-50.00"),
        )
        assert entry.amount == Decimal("-50.00")

    def test_date_is_optional(self):
        entry = DeductionEntry(
            invoice_number="INV-2024-004",
            reason_code="51",
            amount=Decimal("75.00"),
        )
        assert entry.deduction_date is None


class TestRemittanceStub:
    def test_accepts_valid_stub(self):
        stub = RemittanceStub(
            retailer=RetailerFormat.WALMART,
            check_number="CHK-98765",
            payment_date=date(2024, 7, 1),
            gross_invoice=Decimal("10000.00"),
            net_cash=Decimal("9500.00"),
            payer_name="National Mass Retailer",
            deductions=[
                DeductionEntry(
                    invoice_number="INV-001",
                    reason_code="22",
                    amount=Decimal("300.00"),
                ),
                DeductionEntry(
                    invoice_number="INV-001",
                    reason_code="41",
                    amount=Decimal("200.00"),
                ),
            ],
        )
        assert stub.gross_invoice == Decimal("10000.00")
        assert len(stub.deductions) == 2

    def test_rejects_negative_gross_invoice(self):
        with pytest.raises(ValidationError) as exc_info:
            RemittanceStub(
                retailer=RetailerFormat.WALMART,
                check_number="CHK-00001",
                payment_date=date(2024, 7, 1),
                gross_invoice=Decimal("-100.00"),
                net_cash=Decimal("0"),
                payer_name="National Mass Retailer",
            )
        assert "greater than or equal to 0" in str(exc_info.value)

    def test_rejects_invalid_date_format(self):
        with pytest.raises(ValidationError):
            RemittanceStub(
                retailer=RetailerFormat.WALMART,
                check_number="CHK-00001",
                payment_date="not-a-date",
                gross_invoice=Decimal("1000.00"),
                net_cash=Decimal("900.00"),
                payer_name="National Mass Retailer",
            )

    def test_empty_deductions_list_is_valid(self):
        stub = RemittanceStub(
            retailer=RetailerFormat.COSTCO,
            check_number="CHK-11111",
            payment_date=date(2024, 8, 1),
            gross_invoice=Decimal("5000.00"),
            net_cash=Decimal("5000.00"),
            payer_name="Club Retailer",
        )
        assert stub.deductions == []

    def test_source_file_is_optional(self):
        stub = RemittanceStub(
            retailer=RetailerFormat.UNFI,
            check_number="CHK-22222",
            payment_date=date(2024, 9, 1),
            gross_invoice=Decimal("8000.00"),
            net_cash=Decimal("7200.00"),
            payer_name="Distributor A",
        )
        assert stub.source_file is None


class TestValidationResult:
    def test_verified_result(self):
        result = ValidationResult(
            stub_id="stub-001",
            status=ValidationStatus.VERIFIED,
            arithmetic_valid=True,
            all_codes_mapped=True,
        )
        assert result.status == ValidationStatus.VERIFIED
        assert result.discrepancy_amount is None

    def test_flagged_result_with_discrepancy(self):
        result = ValidationResult(
            stub_id="stub-002",
            status=ValidationStatus.FLAGGED,
            arithmetic_valid=False,
            all_codes_mapped=True,
            discrepancy_amount=Decimal("42.50"),
            details=[
                ValidationDetail(
                    field="net_cash",
                    issue="Arithmetic mismatch",
                    expected="9500.00",
                    actual="9457.50",
                )
            ],
        )
        assert result.discrepancy_amount == Decimal("42.50")
        assert len(result.details) == 1


class TestReconciliationResult:
    def test_matched_result(self):
        result = ReconciliationResult(
            stub_id="stub-001",
            match_status=ReconciliationMatch.MATCHED,
            matched_amount=Decimal("10000.00"),
            unmatched_amount=Decimal("0"),
            dispute_window_days_remaining=45,
        )
        assert result.match_status == ReconciliationMatch.MATCHED
        assert result.dispute_window_days_remaining == 45


class TestReasonCodeLoading:
    def test_loads_walmart_codes(self):
        codes = load_reason_codes(RetailerFormat.WALMART)
        assert "22" in codes
        assert codes["22"].category == DeductionCategory.LOGISTICS
        assert codes["22"].description == "Shortage - quantities received differ from invoice"

    def test_loads_costco_codes(self):
        codes = load_reason_codes(RetailerFormat.COSTCO)
        assert "AD" in codes
        assert codes["AD"].category == DeductionCategory.PROMOTIONAL

    def test_loads_unfi_codes(self):
        codes = load_reason_codes(RetailerFormat.UNFI)
        assert "MCB" in codes
        assert codes["MCB"].category == DeductionCategory.PROMOTIONAL

    def test_loads_kehe_codes(self):
        codes = load_reason_codes(RetailerFormat.KEHE)
        assert "MKD" in codes
        assert codes["MKD"].category == DeductionCategory.PROMOTIONAL

    def test_all_retailers_have_at_least_5_codes(self):
        for retailer in RetailerFormat:
            codes = load_reason_codes(retailer)
            assert len(codes) >= 5, f"{retailer.value} has only {len(codes)} codes"

    def test_mapped_code_returns_true(self):
        assert is_reason_code_mapped("22", RetailerFormat.WALMART) is True

    def test_unmapped_code_returns_false(self):
        assert is_reason_code_mapped("ZZ", RetailerFormat.WALMART) is False

    def test_unmapped_code_for_unknown_format(self):
        assert is_reason_code_mapped("22", RetailerFormat.COSTCO) is False
