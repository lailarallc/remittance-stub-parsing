"""Costco remittance stub generator.

Format: "COSTCO WHOLESALE -- REMITTANCE DETAIL"
2-letter alpha codes (AD, DM, FR, MK, PR, SH, etc.)
Different column layout: wider description, vendor number column.
"""

from pathlib import Path

from fpdf import FPDF

from src.models import DeductionEntry, RemittanceStub, RetailerFormat

from .base import (
    BaseStubGenerator,
    quantize_cents,
    random_amount,
    random_invoice_number,
    random_payment_date,
    sanitize_for_pdf,
)


class CostcoStubGenerator(BaseStubGenerator):
    retailer = RetailerFormat.COSTCO
    payer_name = "Club Retailer"
    header_title = "CLUB RETAILER -- REMITTANCE DETAIL"
    invoice_prefix = "CS"

    def render_pdf(self, pdf: FPDF, stub: RemittanceStub) -> None:
        """Render Costco-format stub with alpha reason codes and vendor number."""
        self.render_header(pdf, stub)

        # Vendor info line (Costco-specific)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(0, 6, f"Vendor #: V{self.rng.randint(100000, 999999)}    Warehouse: #{self.rng.randint(100, 999)}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        # Table header — Costco uses wider description, separate code column
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_fill_color(200, 200, 220)

        col_widths = [30, 18, 65, 28, 29]
        headers = ["Ref #", "Code", "Description", "Inv Amount", "Deduction"]

        for header, width in zip(headers, col_widths):
            pdf.cell(width, 8, header, border=1, fill=True, align="C")
        pdf.ln()

        # Table rows
        pdf.set_font("Courier", "", 9)
        for deduction in stub.deductions:
            ref_num = f"R{self.rng.randint(10000, 99999)}"
            inv_amount = quantize_cents(deduction.amount + random_amount(self.rng, 500.0, 8000.0))

            pdf.cell(col_widths[0], 7, ref_num, border=1)
            pdf.cell(col_widths[1], 7, deduction.reason_code, border=1, align="C")
            pdf.cell(col_widths[2], 7, sanitize_for_pdf(deduction.reason_description[:32]), border=1)
            pdf.cell(col_widths[3], 7, f"${inv_amount:,.2f}", border=1, align="R")
            pdf.cell(col_widths[4], 7, f"(${deduction.amount:,.2f})", border=1, align="R")
            pdf.ln()

        self.render_totals(pdf, stub)

    def build_broken_stub_unmapped_code(self, output_path: Path) -> RemittanceStub:
        """Build a Costco stub containing reason code 'XX' which is not in the YAML config."""
        stub = self.build_clean_stub(output_path)

        # Replace one deduction's reason code with unmapped "XX"
        bad_deduction = DeductionEntry(
            invoice_number=random_invoice_number(self.invoice_prefix, self.rng),
            reason_code="XX",
            reason_description="Unknown adjustment",
            amount=random_amount(self.rng, 200.0, 1500.0),
            deduction_date=random_payment_date(self.rng),
        )

        # Recalculate so it still balances arithmetically (the only defect is the code)
        deductions = list(stub.deductions) + [bad_deduction]
        total_deductions = sum(d.amount for d in deductions)
        gross_invoice = quantize_cents(stub.net_cash + total_deductions)

        return RemittanceStub(
            retailer=stub.retailer,
            check_number=stub.check_number,
            payment_date=stub.payment_date,
            gross_invoice=gross_invoice,
            net_cash=stub.net_cash,
            payer_name=stub.payer_name,
            deductions=deductions,
            source_file=output_path.name,
        )

    def generate(self, output_dir: Path) -> list[Path]:
        """Generate clean stubs plus one broken-unmapped-code stub."""
        paths = super().generate(output_dir)

        # Broken stub: unmapped reason code
        broken_path = output_dir / "club_retailer_stub_broken_unmapped_code.pdf"
        broken_stub = self.build_broken_stub_unmapped_code(broken_path)
        self.write_stub_pdf(broken_stub, broken_path)
        paths.append(broken_path)

        return paths
