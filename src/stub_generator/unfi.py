"""UNFI remittance stub generator.

Format: "UNFI -- DISTRIBUTOR SETTLEMENT STATEMENT"
3-letter codes (MCB, OSD, SPA, FRT, DAM, etc.)
Many line items — intentionally multi-page to exercise page handling.
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


class UnfiStubGenerator(BaseStubGenerator):
    retailer = RetailerFormat.UNFI
    payer_name = "Distributor A"
    header_title = "DISTRIBUTOR A -- SETTLEMENT STATEMENT"
    invoice_prefix = "UNF"

    def render_pdf(self, pdf: FPDF, stub: RemittanceStub) -> None:
        """Render UNFI-format stub with settlement-style layout.

        For multi-page stubs, the table header repeats on each page.
        """
        self.render_header(pdf, stub)

        # DC info line
        pdf.set_font("Helvetica", "", 9)
        dc_id = self.rng.randint(1, 30)
        pdf.cell(0, 6, f"Distribution Center: DC-{dc_id:03d}    Region: {self.rng.choice(['East', 'West', 'Central', 'Southeast', 'Northwest'])}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 6, f"Settlement Period: {stub.payment_date.replace(day=1).isoformat()} to {stub.payment_date.isoformat()}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        col_widths = [28, 18, 55, 22, 22, 25]
        headers_row = ["Invoice #", "Code", "Description", "Qty", "Unit $", "Total"]

        self._render_table_header(pdf, headers_row, col_widths)

        # Table rows — UNFI stubs have many line items
        pdf.set_font("Courier", "", 8)
        page_num = 1
        for i, deduction in enumerate(stub.deductions):
            # Check if we need a new page
            if pdf.get_y() > pdf.h - 35:
                self.render_page_footer(pdf, page_num, self._estimate_pages(len(stub.deductions)))
                pdf.add_page()
                page_num += 1
                self._render_table_header(pdf, headers_row, col_widths)
                pdf.set_font("Courier", "", 8)

            qty = self.rng.randint(1, 48)
            unit_price = quantize_cents(deduction.amount / qty) if qty > 0 else deduction.amount

            pdf.cell(col_widths[0], 6, deduction.invoice_number[:10], border=1)
            pdf.cell(col_widths[1], 6, deduction.reason_code, border=1, align="C")
            pdf.cell(col_widths[2], 6, sanitize_for_pdf(deduction.reason_description[:28]), border=1)
            pdf.cell(col_widths[3], 6, str(qty), border=1, align="C")
            pdf.cell(col_widths[4], 6, f"${unit_price:,.2f}", border=1, align="R")
            pdf.cell(col_widths[5], 6, f"${deduction.amount:,.2f}", border=1, align="R")
            pdf.ln()

        self.render_totals(pdf, stub)
        self.render_page_footer(pdf, page_num, page_num)

    def _render_table_header(self, pdf: FPDF, headers: list[str], col_widths: list[int]) -> None:
        """Render the UNFI table header row."""
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(230, 240, 230)
        for header, width in zip(headers, col_widths):
            pdf.cell(width, 7, header, border=1, fill=True, align="C")
        pdf.ln()

    def _estimate_pages(self, num_items: int) -> int:
        """Estimate total page count from line item count."""
        items_first_page = 28
        items_per_page = 35
        if num_items <= items_first_page:
            return 1
        return 1 + ((num_items - items_first_page + items_per_page - 1) // items_per_page)

    def build_multipage_stub(self, output_path: Path) -> RemittanceStub:
        """Build a stub with enough line items to span multiple pages (40+ items)."""
        num_deductions = self.rng.randint(40, 55)
        code_keys = list(self.reason_codes.keys())

        deductions = []
        for _ in range(num_deductions):
            code = self.rng.choice(code_keys)
            desc = self.reason_codes[code].description
            amount = random_amount(self.rng, 30.0, 2000.0)
            inv_num = random_invoice_number(self.invoice_prefix, self.rng)
            deductions.append(
                DeductionEntry(
                    invoice_number=inv_num,
                    reason_code=code,
                    reason_description=desc,
                    amount=amount,
                    deduction_date=random_payment_date(self.rng),
                )
            )

        total_deductions = sum(d.amount for d in deductions)
        net_cash = random_amount(self.rng, 15000.0, 45000.0)
        gross_invoice = quantize_cents(net_cash + total_deductions)

        return RemittanceStub(
            retailer=self.retailer,
            check_number=str(self.rng.randint(10000000, 99999999)),
            payment_date=random_payment_date(self.rng),
            gross_invoice=gross_invoice,
            net_cash=net_cash,
            payer_name=self.payer_name,
            deductions=deductions,
            source_file=output_path.name,
        )

    def generate(self, output_dir: Path) -> list[Path]:
        """Generate clean stubs plus one multi-page stub."""
        paths = super().generate(output_dir)

        # Multi-page stub with 40+ line items
        multipage_path = output_dir / "distributor_a_stub_multipage.pdf"
        multipage_stub = self.build_multipage_stub(multipage_path)
        self.write_stub_pdf(multipage_stub, multipage_path)
        paths.append(multipage_path)

        return paths
