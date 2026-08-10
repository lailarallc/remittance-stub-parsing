"""Reconciliation against Cinderhaven SSOT data.

Matches deduction invoice numbers against reference invoice records
to determine how much of a stub's deductions can be verified against
the accounts-receivable ledger. Also calculates dispute window
exposure — days remaining before unreconciled deductions expire
past the standard 90-day dispute window.
"""

from datetime import date
from decimal import Decimal

from src.models import ReconciliationMatch, ReconciliationResult, RemittanceStub

# Cinderhaven canonical figures
ANNUAL_TRADE_SPEND = Decimal("3600000")  # ~$3.6M/yr
TOTAL_CHARGEBACKS = 3357
DISPUTE_WINDOW_DAYS = 90  # standard dispute window

def reconcile_stub(
    stub: RemittanceStub,
    reference_invoices: dict,
    *,
    dispute_window_days: int,
    stub_id: str = "",
    as_of_date: date,
) -> ReconciliationResult:
    """Reconcile a stub's deductions against Cinderhaven reference invoice data.

    Args:
        stub: The remittance stub to reconcile.
        reference_invoices: Dict mapping invoice_number -> {"amount": Decimal, "date": date}.
        dispute_window_days: REQUIRED, keyword-only — the dispute window (days) the
            "days remaining" math is measured against. Deliberately has no default:
            this value also drives the rendered window label in the caller, and a
            defaulted parameter is exactly how a caption ("45-day window") and its
            math (a hardcoded 90) silently diverge. Forgetting to pass it is a loud
            TypeError, not a wrong number. ``DISPUTE_WINDOW_DAYS`` is the standard
            value callers pass when they have no per-engagement override.
        stub_id: Identifier for this stub. Defaults to check_number.
        as_of_date: REQUIRED, keyword-only — the "as of now" date the dispute-window
            "days remaining" is measured from (the reconciliation/report date, NOT the
            data-window end). Deliberately has no default and no module-constant
            fallback: like dispute_window_days it drives the math AND the caller's
            rendered "computed as of" label, so a silent default is exactly how a
            caption and its math diverge. Forgetting it is a loud TypeError, not a
            wrong (and never-recomputed-against-the-live-calendar) number.

    Returns:
        ReconciliationResult with match status, matched/unmatched amounts,
        and days remaining in the dispute window.
    """
    effective_id = stub_id or stub.check_number
    as_of = as_of_date

    matched_amount = Decimal("0")
    unmatched_amount = Decimal("0")
    details: list[str] = []
    min_days_remaining: int | None = None

    for deduction in stub.deductions:
        invoice_key = deduction.invoice_number

        if invoice_key in reference_invoices:
            ref = reference_invoices[invoice_key]
            ref_amount = Decimal(str(ref["amount"]))

            if ref_amount == deduction.amount:
                matched_amount += deduction.amount
                details.append(
                    f"MATCHED: {invoice_key} — ${deduction.amount} "
                    f"matches reference exactly"
                )
            else:
                # Partial match — amounts differ. Recoverable (unmatched) is
                # only the portion of the deduction NOT backed by the reference
                # invoice. When the reference amount exceeds the deduction, the
                # whole deduction is covered, so nothing is unmatched — adding
                # abs(deduction - ref) here would overstate recoverable dollars.
                matched_amount += min(deduction.amount, ref_amount)
                unmatched_portion = max(Decimal("0"), deduction.amount - ref_amount)
                unmatched_amount += unmatched_portion
                details.append(
                    f"PARTIAL: {invoice_key} — deduction ${deduction.amount} "
                    f"vs reference ${ref_amount} (unmatched ${unmatched_portion})"
                )
        else:
            unmatched_amount += deduction.amount
            details.append(
                f"UNMATCHED: {invoice_key} — ${deduction.amount} "
                f"has no reference invoice"
            )

        # Calculate dispute window from deduction date
        deduction_date = deduction.deduction_date or stub.payment_date
        if deduction_date:
            days_elapsed = (as_of - deduction_date).days
            # Clamp to [0, dispute_window_days]: a deduction dated after the
            # as-of date must never report more than a full window remaining.
            # The window is the caller-supplied value, NOT the module constant —
            # so the split this feeds matches the window the caller labels.
            days_remaining = min(
                dispute_window_days,
                max(0, dispute_window_days - days_elapsed),
            )
            if min_days_remaining is None or days_remaining < min_days_remaining:
                min_days_remaining = days_remaining

    # Determine overall match status
    if unmatched_amount == Decimal("0") and matched_amount > Decimal("0"):
        match_status = ReconciliationMatch.MATCHED
    elif matched_amount > Decimal("0") and unmatched_amount > Decimal("0"):
        match_status = ReconciliationMatch.PARTIAL
    else:
        match_status = ReconciliationMatch.UNMATCHED

    return ReconciliationResult(
        stub_id=effective_id,
        match_status=match_status,
        matched_amount=matched_amount,
        unmatched_amount=unmatched_amount,
        dispute_window_days_remaining=min_days_remaining,
        details=details,
    )
