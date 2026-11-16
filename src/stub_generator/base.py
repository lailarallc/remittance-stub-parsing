"""Base class and shared FPDF2 utilities for synthetic remittance stub generation."""

import random
from abc import ABC, abstractmethod
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from fpdf import FPDF

from src.models import DeductionEntry, RemittanceStub, RetailerFormat, load_reason_codes


# Deterministic seeding -- callers set this before generating
DEFAULT_SEED = 42


def sanitize_for_pdf(text: str) -> str:
    """Replace non-latin-1 characters with safe ASCII equivalents.

    FPDF2 built-in fonts (Helvetica, Courier) only support latin-1.
    Any character outside latin-1 is dropped via encode/decode round-trip
    after explicit substitutions for common typographic characters.
    """
    replacements = {
        "—": "--",  # em-dash
        "–": "-",   # en-dash
        "‘": "'",   # left single quote
        "’": "'",   # right single quote
        "“": '"',   # left double quote
        "”": '"',   # right double quote
        "…": "...", # ellipsis
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    # Final safety net: drop anything that still cannot encode to latin-1
    return text.encode("latin-1", errors="replace").decode("latin-1")


def quantize_cents(amount: Decimal) -> Decimal:
    """Round a Decimal to exactly two decimal places."""
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def random_invoice_number(prefix: str, rng: random.Random) -> str:
    """Generate a realistic invoice number with a prefix."""
    return f"{prefix}-{rng.randint(100000, 999999)}"


def random_check_number(rng: random.Random) -> str:
    """Generate a realistic check number."""
    return str(rng.randint(10000000, 99999999))


def random_payment_date(rng: random.Random) -> date:
    """Generate a payment date within the Cinderhaven data window (2024-2026)."""
    start = date(2024, 3, 1)
    end = date(2026, 9, 30)
    delta = (end - start).days
    return start + timedelta(days=rng.randint(0, delta))


def random_amount(rng: random.Random, low: float = 50.0, high: float = 5000.0) -> Decimal:
    """Generate a random dollar amount, quantized to cents."""
    return quantize_cents(Decimal(str(round(rng.uniform(low, high), 2))))


class BaseStubGenerator(ABC):
    """Abstract base class for retailer-specific stub generators."""

    retailer: RetailerFormat
    payer_name: str
    header_title: str
    invoice_prefix: str

    def __init__(self, seed: int = DEFAULT_SEED):
        self.rng = random.Random(seed)
        self.reason_codes = load_reason_codes(self.retailer)

    @abstractmethod
    def render_pdf(self, pdf: FPDF, stub: RemittanceStub) -> None:
        """Render a single stub onto the FPDF instance. Subclasses implement layout."""

    def build_clean_stub(self, output_path: Path) -> RemittanceStub:
        """Build a stub where net_cash + sum(deductions) = gross_invoice exactly."""
        num_deductions = self.rng.randint(3, 8)
        code_keys = list(self.reason_codes.keys())

        deductions = []
        for _ in range(num_deductions):
            code = self.rng.choice(code_keys)
            desc = self.reason_codes[code].description
            amount = random_amount(self.rng, 80.0, 3500.0)
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
        # Gross invoice: deductions plus a realistic net payment
        net_cash = random_amount(self.rng, 5000.0, 25000.0)
        gross_invoice = quantize_cents(net_cash + total_deductions)

        return RemittanceStub(
            retailer=self.retailer,
            check_number=random_check_number(self.rng),
            payment_date=random_payment_date(self.rng),
            gross_invoice=gross_invoice,
            net_cash=net_cash,
            payer_name=self.payer_name,
            deductions=deductions,
            source_file=output_path.name,
        )

    def write_stub_pdf(self, stub: RemittanceStub, output_path: Path) -> Path:
        """Render a RemittanceStub to a PDF file and return the path."""
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=20)
        pdf.add_page()
        self.render_pdf(pdf, stub)
        pdf.output(str(output_path))
        return output_path

    def generate(self, output_dir: Path) -> list[Path]:
        """Generate a set of clean stubs and return their file paths."""
        output_dir.mkdir(parents=True, exist_ok=True)
        paths = []

        # Generate 3 clean stubs per retailer
        for i in range(3):
            filename = f"{self.retailer.file_slug}_stub_{i + 1:02d}.pdf"
            output_path = output_dir / filename
            stub = self.build_clean_stub(output_path)
            self.write_stub_pdf(stub, output_path)
            paths.append(output_path)

        return paths

    # --- shared PDF rendering helpers ---

    def render_header(self, pdf: FPDF, stub: RemittanceStub) -> None:
        """Render a professional document header with payer info."""
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 10, self.header_title, new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.ln(2)

        # Horizontal rule
        pdf.set_draw_color(100, 100, 100)
        pdf.set_line_width(0.5)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(6)

        # Payment info block
        pdf.set_font("Helvetica", "", 10)
        col_width = (pdf.w - pdf.l_margin - pdf.r_margin) / 2

        y_start = pdf.get_y()

        # Left column
        pdf.set_xy(pdf.l_margin, y_start)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(col_width, 6, f"Payer: {stub.payer_name}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(col_width, 6, f"Check #: {stub.check_number}", new_x="LMARGIN", new_y="NEXT")

        # Right column
        pdf.set_xy(pdf.l_margin + col_width, y_start)
        pdf.cell(col_width, 6, f"Payment Date: {stub.payment_date.isoformat()}", new_x="LMARGIN", new_y="NEXT", align="R")
        pdf.set_xy(pdf.l_margin + col_width, y_start + 6)
        pdf.cell(col_width, 6, "Vendor: Cinderhaven Artisan Foods", new_x="LMARGIN", new_y="NEXT", align="R")

        pdf.set_y(y_start + 18)
        pdf.ln(4)

    def render_totals(self, pdf: FPDF, stub: RemittanceStub) -> None:
        """Render the gross/deductions/net summary block."""
        pdf.ln(4)
        pdf.set_draw_color(100, 100, 100)
        pdf.set_line_width(0.3)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(4)

        total_deductions = sum(d.amount for d in stub.deductions)

        pdf.set_font("Helvetica", "B", 11)
        summary_col = pdf.w - pdf.r_margin - 60

        pdf.set_x(summary_col)
        pdf.cell(30, 7, "Gross Invoice:", new_x="RIGHT", new_y="LAST")
        pdf.cell(30, 7, f"${stub.gross_invoice:,.2f}", new_x="LMARGIN", new_y="NEXT", align="R")

        pdf.set_x(summary_col)
        pdf.cell(30, 7, "Deductions:", new_x="RIGHT", new_y="LAST")
        pdf.cell(30, 7, f"(${total_deductions:,.2f})", new_x="LMARGIN", new_y="NEXT", align="R")

        pdf.set_x(summary_col)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(30, 7, "Net Cash:", new_x="RIGHT", new_y="LAST")
        pdf.cell(30, 7, f"${stub.net_cash:,.2f}", new_x="LMARGIN", new_y="NEXT", align="R")

    def render_page_footer(self, pdf: FPDF, page_num: int, total_pages: int) -> None:
        """Render a page number footer."""
        pdf.set_y(-15)
        pdf.set_font("Helvetica", "I", 8)
        pdf.cell(0, 10, f"Page {page_num} of {total_pages}", align="C")
