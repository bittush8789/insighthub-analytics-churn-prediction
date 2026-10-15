"""Data schemas, column mappings, and validation contracts."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional


# Canonical column names used throughout the platform
CANONICAL_COLUMNS = [
    "invoice",
    "stock_code",
    "description",
    "quantity",
    "invoice_date",
    "price",
    "customer_id",
    "country",
]

# Variations found in UCI Online Retail II and similar retail exports
COLUMN_MAPPINGS: Dict[str, str] = {
    # Invoice variations
    "invoice": "invoice",
    "invoiceno": "invoice",
    "invoice_no": "invoice",
    "bill_no": "invoice",
    # Stock code variations
    "stockcode": "stock_code",
    "stock_code": "stock_code",
    "sku": "stock_code",
    "item_code": "stock_code",
    # Description variations
    "description": "description",
    "product_name": "description",
    "item_description": "description",
    # Quantity variations
    "quantity": "quantity",
    "qty": "quantity",
    # Invoice Date variations
    "invoicedate": "invoice_date",
    "invoice_date": "invoice_date",
    "order_date": "invoice_date",
    # Price variations
    "price": "price",
    "unitprice": "price",
    "unit_price": "price",
    # Customer ID variations
    "customer id": "customer_id",
    "customer_id": "customer_id",
    "customerid": "customer_id",
    "client_id": "customer_id",
    # Country variations
    "country": "country",
    "region": "country",
}


@dataclass
class IngestionAuditSummary:
    """Summary of data ingestion batch quality and counts."""

    batch_id: str
    total_input_rows: int = 0
    accepted_rows: int = 0
    rejected_rows: int = 0
    duplicate_rows: int = 0
    missing_customer_rows: int = 0
    cancellation_rows: int = 0
    gross_sales: Decimal = Decimal("0.00")
    returns_amount: Decimal = Decimal("0.00")
    net_revenue: Decimal = Decimal("0.00")
    rejection_reasons: Dict[str, int] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert audit summary to dictionary."""
        return {
            "batch_id": self.batch_id,
            "total_input_rows": self.total_input_rows,
            "accepted_rows": self.accepted_rows,
            "rejected_rows": self.rejected_rows,
            "duplicate_rows": self.duplicate_rows,
            "missing_customer_rows": self.missing_customer_rows,
            "cancellation_rows": self.cancellation_rows,
            "gross_sales": float(self.gross_sales),
            "returns_amount": float(self.returns_amount),
            "net_revenue": float(self.net_revenue),
            "rejection_reasons": self.rejection_reasons,
            "errors": self.errors,
            "duration_seconds": (
                (self.end_time - self.start_time).total_seconds()
                if self.start_time and self.end_time
                else 0.0
            ),
        }
