"""Data validation rules, schema checking, and data-quality inspection."""

import logging
from typing import Any, Dict, List, Optional, Set, Tuple
import pandas as pd

from src.data.schemas import COLUMN_MAPPINGS
from src.utils.exceptions import DataValidationError

logger = logging.getLogger(__name__)

# Required core fields necessary to process any retail transaction
MANDATORY_FIELDS = {"invoice", "stock_code", "quantity", "invoice_date", "price"}


def normalize_column_name(col: str) -> str:
    """Normalize raw column headers to lowercase snake_case standard."""
    cleaned = str(col).strip().lower().replace(" ", "_").replace("-", "_")
    return COLUMN_MAPPINGS.get(cleaned, cleaned)


def validate_required_columns(df: pd.DataFrame) -> Dict[str, str]:
    """Verify that all mandatory transaction columns are present.

    Args:
        df: Input DataFrame with raw column headers.

    Returns:
        Mapping of original column names to canonical names.

    Raises:
        DataValidationError: If any mandatory column is missing.
    """
    column_map = {}
    found_canonicals = set()

    for col in df.columns:
        canonical = normalize_column_name(col)
        column_map[col] = canonical
        if canonical in MANDATORY_FIELDS:
            found_canonicals.add(canonical)

    missing = MANDATORY_FIELDS - found_canonicals
    if missing:
        raise DataValidationError(
            f"Input dataset is missing mandatory columns: {sorted(list(missing))}. "
            f"Available mapped columns: {sorted(list(found_canonicals))}."
        )

    return column_map


class DataValidator:
    """Performs row-level validation and categorizes quality anomalies."""

    def __init__(self):
        self.seen_signatures: Set[str] = set()

    def inspect_record(
        self,
        row_idx: int,
        invoice: str,
        stock_code: str,
        quantity: Any,
        price: Any,
        invoice_date: Any,
        customer_id: Optional[str],
        country: Optional[str],
    ) -> Tuple[bool, Optional[str], bool, bool]:
        """Validate an individual transaction line.

        Returns:
            Tuple of:
            - is_valid (bool): Whether the record should be accepted into database
            - rejection_reason (str or None): Reason code if rejected
            - is_cancellation (bool): Whether transaction represents a return/cancellation
            - is_missing_customer (bool): Whether customer identifier is absent
        """
        # 1. Check Invoice and StockCode presence
        inv_str = str(invoice).strip()
        sku_str = str(stock_code).strip()
        if not inv_str or inv_str.lower() in ("nan", "none", ""):
            return False, "MISSING_INVOICE_ID", False, False

        if not sku_str or sku_str.lower() in ("nan", "none", ""):
            return False, "MISSING_STOCK_CODE", False, False

        # 2. Check Price validation (Price <= 0 is invalid commercial line)
        try:
            unit_price = float(price)
            if unit_price <= 0.0:
                return False, "INVALID_PRICE_ZERO_OR_NEGATIVE", False, False
        except (ValueError, TypeError):
            return False, "NON_NUMERIC_PRICE", False, False

        # 3. Check Quantity validation
        try:
            qty = int(quantity)
            if qty == 0:
                return False, "ZERO_QUANTITY", False, False
        except (ValueError, TypeError):
            return False, "NON_NUMERIC_QUANTITY", False, False

        # 4. Check Date validation
        if pd.isna(invoice_date):
            return False, "MISSING_INVOICE_DATE", False, False

        # 5. Check Cancellation & Return conventions
        # UCI conventions: Invoice starting with 'C'/'c' or negative quantity indicates cancellation/return
        is_cancellation = inv_str.upper().startswith("C") or qty < 0

        # 6. Check Customer ID status
        is_missing_customer = (
            customer_id is None
            or pd.isna(customer_id)
            or str(customer_id).strip().lower() in ("", "nan", "none", "0", "0.0")
        )

        # 7. Check Duplicate signature
        date_str = str(invoice_date)
        sig = f"{inv_str}|{sku_str}|{qty}|{unit_price:.4f}|{date_str}"
        if sig in self.seen_signatures:
            # We track duplicates; depending on policy we can allow or reject.
            # In retail transactions identical lines within same invoice can occasionally be legitimate,
            # but duplicate lines with identical date & price are marked.
            pass
        self.seen_signatures.add(sig)

        return True, None, is_cancellation, is_missing_customer
