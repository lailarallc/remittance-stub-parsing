"""KeHE remittance stub generator.

Format: "KeHE DISTRIBUTORS -- REMITTANCE ADVICE"
3-letter codes (MKD, PRO, SLT, DMG, SHR, etc.)
Distinct layout: category grouping, PO reference column.
"""

from fpdf import FPDF

from src.models import RemittanceStub, RetailerFormat

from .base import BaseStubGenerator, sanitize_for_pdf


class KeheStubGenerator(BaseStubGenerator):
    retailer = RetailerFormat.KEHE
    payer_name = "Distributor B"
    header_title = "DISTRIBUTOR B -- REMITTANCE ADVICE"
    invoice_prefix = "KH"

    def render_pdf(self, pdf: FPDF, stub: RemittanceStub) -> None:
        """Render KeHE-format stub with PO references and category subtotals."""
        self.render_header(pdf, stub)

        # KeHE-specific: buyer and division info
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(0, 6, f"Division: {self.rng.choice(['Natural', 'Fresh', 'Specialty'])}    Buyer: {self._random_buyer_name()}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 6, f"Account #: KH-{self.rng.randint(10000, 99999)}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        # Table header — KeHE has a PO # column
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_fill_color(230, 225, 210)

        col_widths = [28, 25, 18, 50, 28, 21]
        headers = ["Invoice #", "PO #", "Code", "Description", "Amount", "Cat"]

        for header, width in zip(headers, col_widths):
            pdf.cell(width, 8, header, border=1, fill=True, align="C")
        pdf.ln()

        # Table rows
        pdf.set_font("Helvetica", "", 9)
        for deduction in stub.deductions:
            po_num = f"PO-{self.rng.randint(100000, 999999)}"
            cat_abbrev = self.reason_codes.get(deduction.reason_code)
            cat_label = cat_abbrev.category.value[:4].upper() if cat_abbrev else "UNKN"

            pdf.cell(col_widths[0], 7, deduction.invoice_number[:10], border=1)
            pdf.cell(col_widths[1], 7, po_num, border=1)
            pdf.cell(col_widths[2], 7, deduction.reason_code, border=1, align="C")
            pdf.cell(col_widths[3], 7, sanitize_for_pdf(deduction.reason_description[:25]), border=1)
            pdf.cell(col_widths[4], 7, f"${deduction.amount:,.2f}", border=1, align="R")
            pdf.cell(col_widths[5], 7, cat_label, border=1, align="C")
            pdf.ln()

        self.render_totals(pdf, stub)

    def _random_buyer_name(self) -> str:
        """Generate a plausible buyer name."""
        first_names = ["Sarah", "James", "Michael", "Lisa", "Robert", "Jennifer"]
        last_names = ["Chen", "Martinez", "Johnson", "Williams", "Brown", "Davis"]
        return f"{self.rng.choice(first_names)} {self.rng.choice(last_names)}"
