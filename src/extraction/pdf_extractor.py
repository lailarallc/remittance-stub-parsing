"""PDF extraction engine for retailer remittance stubs.

Extracts structured data from Walmart, Costco, UNFI, and KeHE remittance
PDFs using pdfplumber. Returns typed Pydantic model instances.
"""

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pdfplumber
import yaml

from src.extraction.plugins import detect_plugin
from src.models import DeductionEntry, RemittanceStub, RetailerFormat

FORMAT_CONFIGS_DIR = Path(__file__).parent.parent / "config" / "format_configs"

# Default table-header labels skipped across formats. A format config may override
# with its own ``header_labels`` list; built-in configs rely on this default so
# their behavior is unchanged.
DEFAULT_HEADER_LABELS = {
    "Invoice #", "Reason Code", "Description", "Amount",
    "Ref #", "Code", "Inv Amount", "Deduction",
    "Qty", "Unit $", "Total",
    "PO #", "Cat",
}


def load_format_config(retailer: RetailerFormat) -> dict:
    """Load the YAML format config for a retailer.

    Returns the parsed dict with column_mapping, amount_format, etc.
    """
    yaml_path = FORMAT_CONFIGS_DIR / f"{retailer.value}.yml"
    if not yaml_path.exists():
        raise FileNotFoundError(f"No format config for {retailer.value}: {yaml_path}")

    with open(yaml_path) as f:
        return yaml.safe_load(f)


def detect_format(pdf_path: Path) -> RetailerFormat:
    """Detect which retailer format a PDF uses by scanning first-page text.

    Raises ValueError if the file is not a recognized format.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {pdf_path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Not a PDF file: {pdf_path}")

    with pdfplumber.open(str(path)) as pdf:
        if not pdf.pages:
            raise ValueError(f"PDF has no pages: {pdf_path}")

        first_page_text = pdf.pages[0].extract_text() or ""

    # Detection is config-driven via the plugin registry (each format config's
    # header_pattern), not a hardcoded list. Built-in configs resolve to the
    # RetailerFormat enum so the demo path is unchanged.
    plugin = detect_plugin(first_page_text)
    if plugin is not None:
        return RetailerFormat(plugin.name)

    raise ValueError(
        f"Unrecognized remittance format in {pdf_path}. "
        f"First-page text does not match any known retailer header pattern."
    )


def parse_amount(text: str) -> Decimal:
    """Parse a dollar amount string into a positive Decimal.

    Handles:
      "$1,234.56"     -> Decimal("1234.56")
      "($1,234.56)"   -> Decimal("1234.56")  (parentheses = deduction, stored positive)
      "1,234.56"      -> Decimal("1234.56")
      "$1234.56"      -> Decimal("1234.56")

    Deductions are always stored as positive values in our model.
    """
    if not text or not text.strip():
        raise ValueError(f"Empty amount string")

    cleaned = text.strip()
    # Remove parentheses (negative indicator in accounting)
    cleaned = cleaned.replace("(", "").replace(")", "")
    # Remove dollar sign and commas
    cleaned = cleaned.replace("$", "").replace(",", "")
    # Strip whitespace
    cleaned = cleaned.strip()

    if not cleaned:
        raise ValueError(f"Amount string contains no numeric content: {text!r}")

    try:
        return Decimal(cleaned)
    except InvalidOperation:
        raise ValueError(f"Cannot parse amount: {text!r}")


def extract_header(text: str, retailer: RetailerFormat) -> dict:
    """Parse check number, payment date, and payer name from header text.

    Returns a dict with keys: check_number, payment_date, payer_name.
    """
    result = {
        "check_number": "",
        "payment_date": None,
        "payer_name": "",
    }

    # Check number: "Check #: 12345678"
    check_match = re.search(r"Check\s*#:\s*(\d+)", text)
    if check_match:
        result["check_number"] = check_match.group(1)

    # Payment date: "Payment Date: 2024-06-13"
    date_match = re.search(r"Payment\s+Date:\s*(\d{4}-\d{2}-\d{2})", text)
    if date_match:
        result["payment_date"] = date.fromisoformat(date_match.group(1))

    # Payer name: "Payer: Walmart Inc." (up to next field or end of line)
    payer_match = re.search(r"Payer:\s*(.+?)(?:\s{2,}|Payment Date:|$)", text, re.MULTILINE)
    if payer_match:
        result["payer_name"] = payer_match.group(1).strip()

    return result


def extract_totals(text: str) -> dict:
    """Parse gross_invoice, total_deductions, and net_cash from footer text.

    Returns a dict with keys: gross_invoice, total_deductions, net_cash.
    All values are Decimal or None if not found.
    """
    result = {
        "gross_invoice": None,
        "total_deductions": None,
        "net_cash": None,
    }

    # Gross Invoice: $18,440.23
    gross_match = re.search(r"Gross\s+Invoice:\s*(\$[\d,]+\.\d{2})", text)
    if gross_match:
        result["gross_invoice"] = parse_amount(gross_match.group(1))

    # Deductions: ($10,330.64)
    ded_match = re.search(r"Deductions:\s*\(?\$?([\d,]+\.\d{2})\)?", text)
    if ded_match:
        result["total_deductions"] = parse_amount(ded_match.group(1))

    # Net Cash: $8,109.59
    net_match = re.search(r"Net\s+Cash:\s*(\$[\d,]+\.\d{2})", text)
    if net_match:
        result["net_cash"] = parse_amount(net_match.group(1))

    return result


def _is_header_row(row: list, format_config: dict) -> bool:
    """Check if a table row is a header row (should be skipped).

    Matches against the known column names for each format.
    """
    if not row:
        return False
    # A format config may declare its own header_labels; otherwise use the
    # shared default (built-in formats rely on the default -> unchanged behavior).
    labels = format_config.get("header_labels")
    header_labels = set(labels) if labels else DEFAULT_HEADER_LABELS
    # If the first cell matches a known header label, it's a header row
    first_cell = (row[0] or "").strip()
    return first_cell in header_labels


def extract_deductions(tables: list, format_config: dict) -> list[DeductionEntry]:
    """Map table rows to DeductionEntry models using column mapping from YAML config.

    Skips header rows. Handles both plain and parenthesized amount formats.
    """
    col_mapping = format_config["column_mapping"]
    amount_col_index = col_mapping["amount"]
    invoice_col_index = col_mapping.get("invoice_number", col_mapping.get("ref_number", 0))
    reason_code_col_index = col_mapping["reason_code"]
    description_col_index = col_mapping["description"]

    deductions = []

    for table in tables:
        for row in table:
            # Skip header rows
            if _is_header_row(row, format_config):
                continue

            # Skip rows that don't have enough columns
            if not row or len(row) <= amount_col_index:
                continue

            # Skip None/empty rows
            if all(cell is None or str(cell).strip() == "" for cell in row):
                continue

            invoice_number = (row[invoice_col_index] or "").strip()
            reason_code = (row[reason_code_col_index] or "").strip()
            description = (row[description_col_index] or "").strip()
            amount_text = (row[amount_col_index] or "").strip()

            # Skip rows where the amount cell doesn't look like a dollar amount
            if not amount_text or "$" not in amount_text:
                continue

            try:
                amount = parse_amount(amount_text)
            except ValueError:
                continue

            deductions.append(
                DeductionEntry(
                    invoice_number=invoice_number,
                    reason_code=reason_code,
                    reason_description=description,
                    amount=amount,
                )
            )

    return deductions


def extract_stub_with_text(pdf_path: Path) -> tuple[RemittanceStub, str]:
    """Extract a RemittanceStub and full PDF text in a single file open.

    Returns (stub, full_text). Use this when you need both the structured
    stub and the raw text (e.g., for LLM extraction in the pipeline).
    """
    path = Path(pdf_path)
    retailer = detect_format(path)
    config = load_format_config(retailer)

    with pdfplumber.open(str(path)) as pdf:
        all_text_parts = []
        all_tables = []

        for page in pdf.pages:
            page_text = page.extract_text() or ""
            all_text_parts.append(page_text)

            page_tables = page.extract_tables()
            all_tables.extend(page_tables)

    full_text = "\n".join(all_text_parts)

    header = extract_header(all_text_parts[0] if all_text_parts else "", retailer)
    totals = extract_totals(full_text)
    deductions = extract_deductions(all_tables, config)

    stub = RemittanceStub(
        retailer=retailer,
        check_number=header["check_number"],
        payment_date=header["payment_date"],
        gross_invoice=totals["gross_invoice"] or Decimal("0"),
        net_cash=totals["net_cash"] or Decimal("0"),
        payer_name=header["payer_name"],
        deductions=deductions,
        source_file=Path(path).name,
    )
    return stub, full_text


def extract_with_plugin(pdf_path: Path, plugin) -> RemittanceStub:
    """Extract a RemittanceStub using an explicit format plugin.

    The client-mode entry point: a client format is a plugin (config drop-in),
    which may not correspond to a built-in ``RetailerFormat``. The stub's
    ``retailer`` is the plugin name (a string for a new client format, coerced to
    the enum for a built-in). Uses the same shared header/totals/deduction parsers
    as the built-in path, driven by the plugin's config.
    """
    path = Path(pdf_path)
    config = plugin.format_config

    with pdfplumber.open(str(path)) as pdf:
        all_text_parts = [page.extract_text() or "" for page in pdf.pages]
        all_tables = []
        for page in pdf.pages:
            all_tables.extend(page.extract_tables())

    full_text = "\n".join(all_text_parts)
    header = extract_header(all_text_parts[0] if all_text_parts else "", plugin.name)
    totals = extract_totals(full_text)
    deductions = extract_deductions(all_tables, config)

    return RemittanceStub(
        retailer=plugin.name,
        check_number=header["check_number"],
        payment_date=header["payment_date"],
        gross_invoice=totals["gross_invoice"] or Decimal("0"),
        net_cash=totals["net_cash"] or Decimal("0"),
        payer_name=header["payer_name"],
        deductions=deductions,
        source_file=Path(path).name,
    )


def extract_stub(pdf_path: Path) -> RemittanceStub:
    """Extract a complete RemittanceStub from a PDF file.

    Top-level orchestrator that:
    1. Detects the retailer format
    2. Loads the format config
    3. Extracts header fields
    4. Extracts tables from all pages (handles multi-page UNFI stubs)
    5. Maps table rows to DeductionEntry models
    6. Extracts footer totals
    7. Returns a complete RemittanceStub model
    """
    stub, _ = extract_stub_with_text(pdf_path)
    return stub
