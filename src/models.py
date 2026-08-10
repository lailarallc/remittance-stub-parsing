import functools
from datetime import date
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, field_validator


class RetailerFormat(str, Enum):
    WALMART = "walmart"
    COSTCO = "costco"
    UNFI = "unfi"
    KEHE = "keHE"

    @property
    def display_name(self) -> str:
        """Human-facing retailer name.

        Jinja's ``|title`` filter mangles the acronym/camelCase retailers
        ("unfi" -> "Unfi", "keHE" -> "Kehe"), so templates use this instead.
        """
        return {
            "walmart": "Walmart",
            "costco": "Costco",
            "unfi": "UNFI",
            "keHE": "KeHE",
        }[self.value]


class DeductionCategory(str, Enum):
    PROMOTIONAL = "promotional"
    LOGISTICS = "logistics"
    COMPLIANCE = "compliance"
    FINANCIAL = "financial"
    OPERATIONAL = "operational"
    UNKNOWN = "unknown"


class ReasonCode(BaseModel):
    code: str
    category: DeductionCategory
    description: str


class DeductionEntry(BaseModel):
    invoice_number: str
    reason_code: str
    reason_description: str = ""
    amount: Decimal = Field(description="Positive = deduction from payment")
    deduction_date: Optional[date] = None


def retailer_display_name(retailer) -> str:
    """Human-facing name for a stub's retailer, whether a built-in enum member
    or a client plugin's string name."""
    if isinstance(retailer, RetailerFormat):
        return retailer.display_name
    return str(retailer).replace("_", " ").title()


class RemittanceStub(BaseModel):
    # A built-in format is a RetailerFormat enum member (the demo path); a client
    # plugin format that isn't a built-in is carried as its string name. The
    # validator coerces known values to the enum so built-ins are unchanged.
    retailer: RetailerFormat | str
    check_number: str

    @field_validator("retailer", mode="before")
    @classmethod
    def _coerce_retailer(cls, v):
        if isinstance(v, RetailerFormat):
            return v
        if isinstance(v, str):
            try:
                return RetailerFormat(v)
            except ValueError:
                return v
        return v
    payment_date: Optional[date] = None
    gross_invoice: Decimal = Field(ge=0)
    net_cash: Decimal
    payer_name: str
    deductions: list[DeductionEntry] = []
    source_file: Optional[str] = None


class ValidationStatus(str, Enum):
    VERIFIED = "verified"
    FLAGGED = "flagged"


class ValidationDetail(BaseModel):
    field: str
    issue: str
    expected: Optional[str] = None
    actual: Optional[str] = None


class ValidationResult(BaseModel):
    stub_id: str
    status: ValidationStatus
    arithmetic_valid: bool
    all_codes_mapped: bool
    discrepancy_amount: Optional[Decimal] = None
    details: list[ValidationDetail] = []


class ReconciliationMatch(str, Enum):
    MATCHED = "matched"
    UNMATCHED = "unmatched"
    PARTIAL = "partial"


class ReconciliationResult(BaseModel):
    stub_id: str
    match_status: ReconciliationMatch
    matched_amount: Decimal = Decimal("0")
    unmatched_amount: Decimal = Decimal("0")
    dispute_window_days_remaining: Optional[int] = None
    details: list[str] = []


CONFIG_DIR = Path(__file__).parent / "config"
REASON_CODES_DIR = CONFIG_DIR / "reason_codes"


@functools.lru_cache(maxsize=8)
def load_reason_codes(retailer: RetailerFormat) -> dict[str, ReasonCode]:
    """Load reason-code mapping from the retailer's YAML config.

    Returns a dict keyed by reason code string.
    """
    yaml_path = REASON_CODES_DIR / f"{retailer.value}.yml"
    if not yaml_path.exists():
        raise FileNotFoundError(f"No reason-code config for {retailer.value}: {yaml_path}")

    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    codes = {}
    for code_str, entry in data.get("codes", {}).items():
        codes[str(code_str)] = ReasonCode(
            code=str(code_str),
            category=DeductionCategory(entry["category"]),
            description=entry["description"],
        )
    return codes


def is_reason_code_mapped(code: str, retailer: RetailerFormat) -> bool:
    """Check whether a reason code exists in the retailer's config."""
    try:
        codes = load_reason_codes(retailer)
    except FileNotFoundError:
        return False
    return code in codes
