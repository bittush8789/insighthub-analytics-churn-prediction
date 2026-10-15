"""Data cleaning, normalization, and reconciliation of gross sales, returns, and net revenue."""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple
import pandas as pd

from src.data.schemas import IngestionAuditSummary
from src.data.validation import DataValidator, validate_required_columns
from src.utils.helpers import generate_line_hash, to_decimal

logger = logging.getLogger(__name__)


def parse_datetime_safe(date_val: Any) -> Optional[datetime]:
    """Parse transaction dates with support for various retail timestamp formats."""
    if pd.isna(date_val):
        return None
    if isinstance(date_val, datetime):
        return date_val
    if isinstance(date_val, pd.Timestamp):
        return date_val.to_pydatetime()

    val_str = str(date_val).strip()
    # Try common formats
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%m/%d/%Y %H:%M",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(val_str, fmt)
        except ValueError:
            continue

    # Fallback to dateutil/pandas
    try:
        dt = pd.to_datetime(val_str)
        return dt.to_pydatetime()
    except Exception:
        return None


def clean_and_normalize_data(
    df: pd.DataFrame, batch_id: str
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], IngestionAuditSummary]:
    """Clean, validate, and prepare normalized records for database persistence.

    Returns:
        Tuple containing:
        1. customers_to_upsert: List of unique customer dictionaries
        2. products_to_upsert: List of unique product dictionaries
        3. orders_to_insert: List of order header dictionaries
        4. items_to_insert: List of order line item dictionaries
        5. summary: IngestionAuditSummary capturing data quality statistics
    """
    summary = IngestionAuditSummary(batch_id=batch_id, start_time=datetime.now())
    summary.total_input_rows = len(df)

    # 1. Validate mandatory columns and map headers
    col_map = validate_required_columns(df)
    renamed_df = df.rename(columns=col_map)

    validator = DataValidator()
    rejected_records: List[Dict[str, Any]] = []

    customers_map: Dict[str, Dict[str, Any]] = {}
    products_map: Dict[str, Dict[str, Any]] = {}
    orders_map: Dict[str, Dict[str, Any]] = {}
    items_list: List[Dict[str, Any]] = []

    seen_line_signatures: Set[str] = set()

    for row_idx, row in renamed_df.iterrows():
        raw_inv = row.get("invoice")
        raw_sku = row.get("stock_code")
        raw_qty = row.get("quantity")
        raw_price = row.get("price")
        raw_date = row.get("invoice_date")
        raw_cust = row.get("customer_id")
        raw_country = row.get("country", "Unknown")
        raw_desc = row.get("description", "Unknown Product")

        # Row-level validation
        is_valid, reason, is_cancellation, is_missing_customer = validator.inspect_record(
            row_idx=row_idx,
            invoice=raw_inv,
            stock_code=raw_sku,
            quantity=raw_qty,
            price=raw_price,
            invoice_date=raw_date,
            customer_id=raw_cust,
            country=raw_country,
        )

        if not is_valid:
            summary.rejected_rows += 1
            summary.rejection_reasons[reason] = summary.rejection_reasons.get(reason, 0) + 1
            rejected_records.append({
                "batch_id": batch_id,
                "row_number": int(row_idx) + 1,
                "rejection_reason": reason,
                "raw_record": str(row.to_dict()),
            })
            continue

        parsed_date = parse_datetime_safe(raw_date)
        if not parsed_date:
            summary.rejected_rows += 1
            r_reason = "INVALID_DATE_PARSING"
            summary.rejection_reasons[r_reason] = summary.rejection_reasons.get(r_reason, 0) + 1
            rejected_records.append({
                "batch_id": batch_id,
                "row_number": int(row_idx) + 1,
                "rejection_reason": r_reason,
                "raw_record": str(row.to_dict()),
            })
            continue

        # Validated fields
        order_id = str(raw_inv).strip()
        product_id = str(raw_sku).strip()
        product_name = str(raw_desc).strip() if pd.notna(raw_desc) and str(raw_desc).strip() else "Unknown Product"
        country_str = str(raw_country).strip() if pd.notna(raw_country) and str(raw_country).strip() else "Unknown"

        # Customer ID cleaning (remove decimal '.0' if float representation)
        cust_id_clean: Optional[str] = None
        if not is_missing_customer:
            cust_val_str = str(raw_cust).strip()
            if cust_val_str.endswith(".0"):
                cust_val_str = cust_val_str[:-2]
            cust_id_clean = cust_val_str
        else:
            summary.missing_customer_rows += 1

        qty = int(raw_qty)
        unit_price_float = float(raw_price)
        unit_price_dec = to_decimal(unit_price_float)

        # Monetary math (Strict Decimal)
        # Note: Cancellations have negative quantity, so line_total is negative
        line_total_dec = Decimal(qty) * unit_price_dec

        # Check duplicate line within batch
        line_sig = f"{order_id}|{product_id}|{qty}|{unit_price_float:.4f}|{parsed_date.isoformat()}"
        if line_sig in seen_line_signatures:
            summary.duplicate_rows += 1
        seen_line_signatures.add(line_sig)

        line_hash = generate_line_hash(order_id, product_id, qty, unit_price_float, row_idx)

        # Tally revenue
        if is_cancellation:
            summary.cancellation_rows += 1
            summary.returns_amount += abs(line_total_dec)
        else:
            summary.gross_sales += line_total_dec

        summary.accepted_rows += 1

        # Track Products
        if product_id not in products_map:
            products_map[product_id] = {
                "product_id": product_id,
                "product_name": product_name[:255],
                "category": "General",
            }
        elif products_map[product_id]["product_name"] == "Unknown Product" and product_name != "Unknown Product":
            products_map[product_id]["product_name"] = product_name[:255]

        # Track Customers
        if cust_id_clean:
            if cust_id_clean not in customers_map:
                customers_map[cust_id_clean] = {
                    "customer_id": cust_id_clean,
                    "country": country_str,
                    "order_date": parsed_date,
                    "order_count_inc": 1,
                }
            else:
                existing_cust = customers_map[cust_id_clean]
                if parsed_date < existing_cust["order_date"]:
                    existing_cust["order_date"] = parsed_date
                existing_cust["order_count_inc"] += 1

        # Track Order Header
        if order_id not in orders_map:
            orders_map[order_id] = {
                "order_id": order_id,
                "customer_id": cust_id_clean,
                "order_date": parsed_date,
                "status": "CANCELLED" if is_cancellation else "COMPLETED",
                "is_cancellation": is_cancellation,
                "country": country_str,
                "gross_amount": line_total_dec if not is_cancellation else Decimal("0.00"),
                "discount_or_return_amount": abs(line_total_dec) if is_cancellation else Decimal("0.00"),
                "net_amount": line_total_dec,
                "batch_id": batch_id,
            }
        else:
            ord_header = orders_map[order_id]
            if is_cancellation:
                ord_header["discount_or_return_amount"] += abs(line_total_dec)
            else:
                ord_header["gross_amount"] += line_total_dec
            ord_header["net_amount"] += line_total_dec

        # Track Line Item
        items_list.append({
            "order_id": order_id,
            "product_id": product_id,
            "quantity": qty,
            "unit_price": unit_price_dec,
            "line_total": line_total_dec,
            "line_hash": line_hash,
        })

    summary.net_revenue = summary.gross_sales - summary.returns_amount
    summary.end_time = datetime.now()

    # Pass rejected_records through summary for persistence
    summary.errors = [f"Row {r['row_number']}: {r['rejection_reason']}" for r in rejected_records[:50]]

    return (
        list(customers_map.values()),
        list(products_map.values()),
        list(orders_map.values()),
        items_list,
        summary,
    )
