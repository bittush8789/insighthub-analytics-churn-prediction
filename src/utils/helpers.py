"""Utility functions for hashing, conversions, and formatting."""

import hashlib
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional


def generate_line_hash(order_id: str, product_id: str, quantity: int, unit_price: float, line_index: int) -> str:
    """Generate deterministic SHA256 hash for idempotent line item tracking.

    Args:
        order_id: Unique invoice or order identifier.
        product_id: Stock code or product SKU.
        quantity: Item quantity (positive or negative for cancellations).
        unit_price: Unit selling price.
        line_index: Positional index in source file to handle repeated identical lines.

    Returns:
        Hexadecimal SHA-256 digest string.
    """
    raw_key = f"{order_id}|{product_id}|{quantity}|{unit_price:.4f}|{line_index}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def to_decimal(val: Any, default: Decimal = Decimal("0.00")) -> Decimal:
    """Safely convert any numeric or string value to Decimal with 2 decimal places.

    Args:
        val: Input numeric, string, or float.
        default: Fallback decimal value if conversion fails.

    Returns:
        Decimal object rounded to two places.
    """
    if val is None:
        return default
    try:
        if isinstance(val, float):
            return Decimal(str(round(val, 4)))
        return Decimal(str(val))
    except (InvalidOperation, TypeError, ValueError):
        return default


def format_currency(value: Any) -> str:
    """Format numeric value as USD/GBP currency string with commas."""
    try:
        val_float = float(value)
        return f"${val_float:,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


def format_percentage(value: Any) -> str:
    """Format numeric float (e.g., 0.125) as percentage string (e.g., '12.5%')."""
    try:
        val_float = float(value)
        return f"{val_float * 100:.1f}%"
    except (TypeError, ValueError):
        return "0.0%"
