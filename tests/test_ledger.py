"""Tests for the SQLite ledger and reconciliation modules."""

from datetime import date
from decimal import Decimal

import pytest

from src.models import (
    DeductionEntry,
    ReconciliationMatch,
    ReconciliationResult,
    RemittanceStub,
    RetailerFormat,
    ValidationResult,
    ValidationStatus,
    ValidationDetail,
)
from src.ledger.database import (
    get_all_stubs,
    get_stub_summary,
    init_database,
    insert_reconciliation_result,
    insert_stub,
    insert_validation_result,
)
from src.ledger.reconciliation import (
    DISPUTE_WINDOW_DAYS,
    reconcile_stub,
)


# --- fixtures ---

@pytest.fixture
def db_conn(tmp_path):
    """Create a fresh in-memory-like SQLite database for each test."""
    db_path = tmp_path / "test_ledger.db"
    conn = init_database(db_path)
    yield conn
    conn.close()


def _make_stub(
    check_number: str = "CHK-001",
    retailer: RetailerFormat = RetailerFormat.WALMART,
    gross: str = "10000.00",
    net: str = "8000.00",
    deductions: list[tuple[str, str, str]] | None = None,
) -> RemittanceStub:
    """Build a RemittanceStub for testing."""
    if deductions is None:
        deductions = [
            ("WM-100001", "22", "1000.00"),
            ("WM-100002", "41", "1000.00"),
        ]

    entries = [
        DeductionEntry(
            invoice_number=inv,
            reason_code=code,
            reason_description="test deduction",
            amount=Decimal(amt),
            deduction_date=date(2025, 6, 1),
        )
        for inv, code, amt in deductions
    ]

    return RemittanceStub(
        retailer=retailer,
        check_number=check_number,
        payment_date=date(2025, 7, 1),
        gross_invoice=Decimal(gross),
        net_cash=Decimal(net),
        payer_name="Test Payer",
        deductions=entries,
    )


# --- database initialization ---

class TestDatabaseInit:
    def test_creates_tables(self, db_conn):
        """All four tables exist after init."""
        cursor = db_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor]
        assert "stubs" in tables
        assert "deductions" in tables
        assert "validation_results" in tables
        assert "reconciliation_results" in tables

    def test_wal_mode_enabled(self, db_conn):
        """WAL journal mode is set for concurrent read performance."""
        mode = db_conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"


# --- stub insertion and retrieval ---

class TestStubInsertRetrieve:
    def test_insert_and_retrieve_stub(self, db_conn):
        """Insert a stub with deductions and retrieve it."""
        stub = _make_stub()
        insert_stub(db_conn, stub, "stub-001")

        stubs = get_all_stubs(db_conn)
        assert len(stubs) == 1
        assert stubs[0]["id"] == "stub-001"
        assert stubs[0]["retailer"] == "walmart"
        assert stubs[0]["gross_invoice"] == "10000.00"
        assert stubs[0]["net_cash"] == "8000.00"
        assert len(stubs[0]["deductions"]) == 2

    def test_deduction_fields_stored_correctly(self, db_conn):
        """Deduction invoice number, code, amount stored as expected."""
        stub = _make_stub()
        insert_stub(db_conn, stub, "stub-002")

        stubs = get_all_stubs(db_conn)
        ded = stubs[0]["deductions"][0]
        assert ded["invoice_number"] == "WM-100001"
        assert ded["reason_code"] == "22"
        assert ded["amount"] == "1000.00"
        assert ded["category"] == "logistics"  # Walmart code 22 = logistics

    def test_insert_replaces_on_same_id(self, db_conn):
        """Inserting with the same stub_id replaces the previous record."""
        stub1 = _make_stub(gross="10000.00")
        stub2 = _make_stub(gross="20000.00")

        insert_stub(db_conn, stub1, "stub-dup")
        insert_stub(db_conn, stub2, "stub-dup")

        stubs = get_all_stubs(db_conn)
        assert len(stubs) == 1
        assert stubs[0]["gross_invoice"] == "20000.00"

    def test_multiple_stubs(self, db_conn):
        """Insert multiple stubs and retrieve all."""
        for i in range(3):
            stub = _make_stub(check_number=f"CHK-{i:03d}")
            insert_stub(db_conn, stub, f"stub-{i:03d}")

        stubs = get_all_stubs(db_conn)
        assert len(stubs) == 3


# --- validation result storage ---

class TestValidationResultStorage:
    def test_insert_and_retrieve_validation(self, db_conn):
        """Insert a validation result and check it persists."""
        stub = _make_stub()
        insert_stub(db_conn, stub, "val-001")

        validation = ValidationResult(
            stub_id="val-001",
            status=ValidationStatus.VERIFIED,
            arithmetic_valid=True,
            all_codes_mapped=True,
        )
        insert_validation_result(db_conn, validation)

        row = db_conn.execute(
            "SELECT * FROM validation_results WHERE stub_id = 'val-001'"
        ).fetchone()
        assert row is not None
        assert row[1] == "verified"  # status column
        assert row[2] == 1  # arithmetic_valid

    def test_flagged_validation_with_details(self, db_conn):
        """Flagged validation stores discrepancy and details JSON."""
        stub = _make_stub()
        insert_stub(db_conn, stub, "val-002")

        validation = ValidationResult(
            stub_id="val-002",
            status=ValidationStatus.FLAGGED,
            arithmetic_valid=False,
            all_codes_mapped=True,
            discrepancy_amount=Decimal("42.50"),
            details=[
                ValidationDetail(
                    field="gross_invoice",
                    issue="Arithmetic mismatch",
                    expected="10000.00",
                    actual="10042.50",
                )
            ],
        )
        insert_validation_result(db_conn, validation)

        row = db_conn.execute(
            "SELECT discrepancy_amount, details_json FROM validation_results "
            "WHERE stub_id = 'val-002'"
        ).fetchone()
        assert row[0] == "42.50"
        assert "Arithmetic mismatch" in row[1]


# --- reconciliation result storage ---

class TestReconciliationResultStorage:
    def test_insert_and_retrieve_reconciliation(self, db_conn):
        """Insert a reconciliation result and check it persists."""
        stub = _make_stub()
        insert_stub(db_conn, stub, "rec-001")

        reconciliation = ReconciliationResult(
            stub_id="rec-001",
            match_status=ReconciliationMatch.PARTIAL,
            matched_amount=Decimal("1000.00"),
            unmatched_amount=Decimal("1000.00"),
            dispute_window_days_remaining=45,
            details=["MATCHED: WM-100001", "UNMATCHED: WM-100002"],
        )
        insert_reconciliation_result(db_conn, reconciliation)

        row = db_conn.execute(
            "SELECT * FROM reconciliation_results WHERE stub_id = 'rec-001'"
        ).fetchone()
        assert row is not None
        assert row[1] == "partial"  # match_status
        assert row[2] == "1000.00"  # matched_amount
        assert row[4] == 45  # dispute_window_days_remaining


# --- summary stats ---

class TestSummaryStats:
    def test_summary_with_multiple_stubs(self, db_conn):
        """Summary counts and totals are correct after inserting stubs."""
        # Insert two stubs
        stub1 = _make_stub(
            check_number="CHK-S1",
            gross="10000.00",
            net="8000.00",
            deductions=[("WM-100001", "22", "2000.00")],
        )
        stub2 = _make_stub(
            check_number="CHK-S2",
            gross="5000.00",
            net="4000.00",
            deductions=[("WM-100002", "41", "1000.00")],
        )
        insert_stub(db_conn, stub1, "sum-001")
        insert_stub(db_conn, stub2, "sum-002")

        # Insert validation results
        insert_validation_result(db_conn, ValidationResult(
            stub_id="sum-001",
            status=ValidationStatus.VERIFIED,
            arithmetic_valid=True,
            all_codes_mapped=True,
        ))
        insert_validation_result(db_conn, ValidationResult(
            stub_id="sum-002",
            status=ValidationStatus.FLAGGED,
            arithmetic_valid=False,
            all_codes_mapped=True,
            discrepancy_amount=Decimal("10.00"),
        ))

        summary = get_stub_summary(db_conn)

        assert summary["total_stubs"] == 2
        assert summary["verified"] == 1
        assert summary["flagged"] == 1
        assert summary["total_gross"] == Decimal("15000.00")
        assert summary["total_net"] == Decimal("12000.00")
        assert summary["total_deductions"] == Decimal("3000.00")

    def test_summary_empty_database(self, db_conn):
        """Summary returns zeros on an empty database."""
        summary = get_stub_summary(db_conn)
        assert summary["total_stubs"] == 0
        assert summary["verified"] == 0
        assert summary["flagged"] == 0
        assert summary["total_gross"] == Decimal("0")


# --- reconciliation logic ---

class TestReconciliation:
    def test_fully_matched_when_all_invoices_found(self):
        """All deductions match reference invoices exactly."""
        stub = _make_stub(
            deductions=[
                ("WM-100001", "22", "500.00"),
                ("WM-100002", "41", "300.00"),
            ],
        )
        reference = {
            "WM-100001": {"amount": Decimal("500.00"), "date": date(2025, 6, 1)},
            "WM-100002": {"amount": Decimal("300.00"), "date": date(2025, 6, 1)},
        }

        result = reconcile_stub(stub, reference, dispute_window_days=DISPUTE_WINDOW_DAYS,
                                as_of_date=date(2026, 7, 30),
                                stub_id="rec-full")

        assert result.match_status == ReconciliationMatch.MATCHED
        assert result.matched_amount == Decimal("800.00")
        assert result.unmatched_amount == Decimal("0")

    def test_unmatched_when_no_invoices_found(self):
        """No deductions match any reference invoice."""
        stub = _make_stub(
            deductions=[
                ("WM-999001", "22", "500.00"),
                ("WM-999002", "41", "300.00"),
            ],
        )
        reference = {
            "WM-100001": {"amount": Decimal("500.00"), "date": date(2025, 6, 1)},
        }

        result = reconcile_stub(stub, reference, dispute_window_days=DISPUTE_WINDOW_DAYS,
                                as_of_date=date(2026, 7, 30),
                                stub_id="rec-none")

        assert result.match_status == ReconciliationMatch.UNMATCHED
        assert result.matched_amount == Decimal("0")
        assert result.unmatched_amount == Decimal("800.00")

    def test_partial_when_amounts_differ(self):
        """Invoice found but amounts differ — partial match."""
        stub = _make_stub(
            deductions=[
                ("WM-100001", "22", "500.00"),
            ],
        )
        reference = {
            "WM-100001": {"amount": Decimal("480.00"), "date": date(2025, 6, 1)},
        }

        result = reconcile_stub(stub, reference, dispute_window_days=DISPUTE_WINDOW_DAYS,
                                as_of_date=date(2026, 7, 30),
                                stub_id="rec-partial")

        assert result.match_status == ReconciliationMatch.PARTIAL
        assert result.matched_amount == Decimal("480.00")  # min of the two
        assert result.unmatched_amount == Decimal("20.00")  # difference

    def test_no_unmatched_when_reference_exceeds_deduction(self):
        """Reference invoice larger than the deduction: whole deduction is
        covered, so recoverable (unmatched) is zero — not abs(diff)."""
        stub = _make_stub(
            deductions=[
                ("WM-100001", "22", "500.00"),
            ],
        )
        reference = {
            "WM-100001": {"amount": Decimal("600.00"), "date": date(2025, 6, 1)},
        }

        result = reconcile_stub(stub, reference, dispute_window_days=DISPUTE_WINDOW_DAYS,
                                as_of_date=date(2026, 7, 30),
                                stub_id="rec-ref-bigger")

        assert result.matched_amount == Decimal("500.00")  # full deduction
        assert result.unmatched_amount == Decimal("0")  # nothing recoverable

    def test_mixed_matched_and_unmatched(self):
        """One deduction matches, one has no reference — partial overall."""
        stub = _make_stub(
            deductions=[
                ("WM-100001", "22", "500.00"),
                ("WM-999999", "41", "300.00"),
            ],
        )
        reference = {
            "WM-100001": {"amount": Decimal("500.00"), "date": date(2025, 6, 1)},
        }

        result = reconcile_stub(stub, reference, dispute_window_days=DISPUTE_WINDOW_DAYS,
                                as_of_date=date(2026, 7, 30),
                                stub_id="rec-mixed")

        assert result.match_status == ReconciliationMatch.PARTIAL
        assert result.matched_amount == Decimal("500.00")
        assert result.unmatched_amount == Decimal("300.00")

    def test_dispute_window_calculation(self):
        """Days remaining calculated from deduction date to as_of_date."""
        stub = _make_stub(
            deductions=[
                ("WM-100001", "22", "500.00"),
            ],
        )
        # Deduction date is 2025-06-01, as_of is 2025-07-01 = 30 days elapsed
        reference = {
            "WM-100001": {"amount": Decimal("500.00"), "date": date(2025, 6, 1)},
        }

        result = reconcile_stub(
            stub, reference,
            dispute_window_days=DISPUTE_WINDOW_DAYS,
            stub_id="rec-window",
            as_of_date=date(2025, 7, 1),
        )

        assert result.dispute_window_days_remaining == 60  # 90 - 30

    def test_dispute_window_expired(self):
        """Days remaining is zero when past the dispute window."""
        stub = _make_stub(
            deductions=[
                ("WM-100001", "22", "500.00"),
            ],
        )
        reference = {
            "WM-100001": {"amount": Decimal("500.00"), "date": date(2025, 6, 1)},
        }

        # 100 days elapsed — past the 90-day window
        result = reconcile_stub(
            stub, reference,
            dispute_window_days=DISPUTE_WINDOW_DAYS,
            stub_id="rec-expired",
            as_of_date=date(2025, 9, 9),
        )

        assert result.dispute_window_days_remaining == 0

    def test_dispute_window_split_tracks_the_supplied_window(self):
        """A 60-day-old deduction is WITHIN a 90-day window (30 days left) but PAST
        a 45-day one (0 days left). days-remaining — which drives the within/past
        split in the caller — must be computed from the SUPPLIED window, not a
        module default. This is the defect the required param closes: the caller
        labeled the window from config while the split silently used a hardcoded
        90 (see ENGAGEMENT-READY-CHECKLIST, remittance worked example)."""
        stub = _make_stub(deductions=[("WM-100001", "22", "500.00")])
        reference = {"WM-100001": {"amount": Decimal("500.00"), "date": date(2025, 6, 1)}}
        # 2025-06-01 -> 2025-07-31 = 60 days elapsed.
        within = reconcile_stub(stub, reference, dispute_window_days=90,
                                stub_id="rec-90", as_of_date=date(2025, 7, 31))
        past = reconcile_stub(stub, reference, dispute_window_days=45,
                              stub_id="rec-45", as_of_date=date(2025, 7, 31))
        assert within.dispute_window_days_remaining == 30   # 90 - 60 -> still disputable
        assert past.dispute_window_days_remaining == 0      # 45 - 60 -> expired

    def test_dispute_window_days_is_required(self):
        """Omitting the window is a loud TypeError, not a silent default to 90 —
        a defaulted param is exactly how the next caller re-introduces the
        caption-vs-math divergence."""
        stub = _make_stub(deductions=[("WM-100001", "22", "500.00")])
        with pytest.raises(TypeError):
            reconcile_stub(stub, {}, stub_id="rec-noarg")

    def test_as_of_date_is_required(self):
        """Omitting as_of_date is a loud TypeError, not a silent fallback to a module
        constant (the AS_OF_DATE hardcode removed in the 0.d split) — same fail-closed
        reasoning as dispute_window_days."""
        stub = _make_stub(deductions=[("WM-100001", "22", "500.00")])
        with pytest.raises(TypeError):
            reconcile_stub(stub, {}, dispute_window_days=DISPUTE_WINDOW_DAYS)

    def test_details_describe_each_deduction(self):
        """Details list has one entry per deduction describing the match."""
        stub = _make_stub(
            deductions=[
                ("WM-100001", "22", "500.00"),
                ("WM-999999", "41", "300.00"),
            ],
        )
        reference = {
            "WM-100001": {"amount": Decimal("500.00"), "date": date(2025, 6, 1)},
        }

        result = reconcile_stub(stub, reference, dispute_window_days=DISPUTE_WINDOW_DAYS,
                                as_of_date=date(2026, 7, 30),
                                stub_id="rec-details")

        assert len(result.details) == 2
        assert "MATCHED" in result.details[0]
        assert "UNMATCHED" in result.details[1]

    def test_uses_check_number_when_no_stub_id(self):
        """Default stub_id falls back to check_number."""
        stub = _make_stub(check_number="CHK-FALLBACK")
        result = reconcile_stub(stub, {}, dispute_window_days=DISPUTE_WINDOW_DAYS,
                                as_of_date=date(2026, 7, 30))
        assert result.stub_id == "CHK-FALLBACK"

    def test_empty_deductions_is_unmatched(self):
        """Stub with no deductions: nothing to match."""
        stub = _make_stub(
            gross="5000.00",
            net="5000.00",
            deductions=[],
        )
        result = reconcile_stub(stub, {}, dispute_window_days=DISPUTE_WINDOW_DAYS,
                                as_of_date=date(2026, 7, 30), stub_id="rec-empty")

        assert result.match_status == ReconciliationMatch.UNMATCHED
        assert result.matched_amount == Decimal("0")
        assert result.unmatched_amount == Decimal("0")


# --- full flow ---

class TestFullFlow:
    def test_extract_validate_reconcile_insert_summary(self, db_conn):
        """End-to-end: build stub, validate, reconcile, insert all, check summary."""
        from src.validation.reason_codes import validate_stub as full_validate

        # 1. Build a clean stub
        stub = _make_stub(
            check_number="CHK-FLOW",
            gross="10000.00",
            net="8000.00",
            deductions=[
                ("WM-100001", "22", "1200.00"),
                ("WM-100002", "41", "800.00"),
            ],
        )
        stub_id = "flow-001"

        # 2. Validate
        validation = full_validate(stub, stub_id=stub_id)
        assert validation.status == ValidationStatus.VERIFIED

        # 3. Reconcile
        reference = {
            "WM-100001": {"amount": Decimal("1200.00"), "date": date(2025, 6, 1)},
        }
        reconciliation = reconcile_stub(
            stub, reference, dispute_window_days=DISPUTE_WINDOW_DAYS,
            stub_id=stub_id, as_of_date=date(2025, 7, 1),
        )
        assert reconciliation.match_status == ReconciliationMatch.PARTIAL

        # 4. Insert everything
        insert_stub(db_conn, stub, stub_id)
        insert_validation_result(db_conn, validation)
        insert_reconciliation_result(db_conn, reconciliation)

        # 5. Verify summary
        summary = get_stub_summary(db_conn)
        assert summary["total_stubs"] == 1
        assert summary["verified"] == 1
        assert summary["total_gross"] == Decimal("10000.00")
        assert summary["total_net"] == Decimal("8000.00")
        assert summary["total_deductions"] == Decimal("2000.00")

        # 6. Verify stubs retrieval
        stubs = get_all_stubs(db_conn)
        assert len(stubs) == 1
        assert len(stubs[0]["deductions"]) == 2
