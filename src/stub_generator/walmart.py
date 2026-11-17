"""Walmart remittance stub generator.

Format: "WALMART INC. -- PAYMENT ADVICE"
Numeric reason codes (22, 41, 42, 51, 72, etc.)
Columns: Invoice #, Reason Code, Description, Amount
"""

from decimal import Decimal
from pathlib import Path

from fpdf import FPDF

from src.models import RemittanceStub, RetailerFormat

from .base import BaseStubGenerator, quantize_cents, sanitize_for_pdf


class WalmartStubGenerator(BaseStubGenerator):
    retailer = RetailerFormat.WALMART
    payer_name = "National Mass Retailer"
    header_title = "NATIONAL MASS RETAILER -- PAYMENT ADVICE"
    invoice_prefix = "WM"

    def render_pdf(self, pdf: FPDF, stub: RemittanceStub) -> None:
        """Render Walmart-format stub with numeric reason codes."""
        self.render_header(pdf, stub)

        # Table header
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_fill_color(220, 220, 220)

        col_widths = [35, 25, 80, 30]
        headers = ["Invoice #", "Reason Code", "Description", "Amount"]

        for header, width in zip(headers, col_widths):
            pdf.cell(width, 8, header, border=1, fill=True, align="C")
        pdf.ln()

        # Table rows
        pdf.set_font("Helvetica", "", 9)
        for deduction in stub.deductions:
            pdf.cell(col_widths[0], 7, deduction.invoice_number, border=1)
            pdf.cell(col_widths[1], 7, deduction.reason_code, border=1, align="C")
            pdf.cell(col_widths[2], 7, sanitize_for_pdf(deduction.reason_description[:40]), border=1)
            pdf.cell(col_widths[3], 7, f"${deduction.amount:,.2f}", border=1, align="R")
            pdf.ln()

        self.render_totals(pdf, stub)

    def build_broken_stub_arithmetic(self, output_path: Path) -> RemittanceStub:
        """Build a Walmart stub with a $42.50 arithmetic discrepancy.

        net_cash + sum(deductions) != gross_invoice deliberately.
        """
        stub = self.build_clean_stub(output_path)

        # Inflate gross_invoice by $42.50 so the math doesn't balance
        broken_gross = quantize_cents(stub.gross_invoice + Decimal("42.50"))

        return RemittanceStub(
            retailer=stub.retailer,
            check_number=stub.check_number,
            payment_date=stub.payment_date,
            gross_invoice=broken_gross,
            net_cash=stub.net_cash,
            payer_name=stub.payer_name,
            deductions=stub.deductions,
            source_file=output_path.name,
        )

    def generate(self, output_dir: Path) -> list[Path]:
        """Generate clean stubs plus one broken-arithmetic stub."""
        paths = super().generate(output_dir)

        # Broken stub: arithmetic discrepancy
        broken_path = output_dir / "mass_retailer_stub_broken_arithmetic.pdf"
        broken_stub = self.build_broken_stub_arithmetic(broken_path)
        self.write_stub_pdf(broken_stub, broken_path)
        paths.append(broken_path)

        return paths
