"""Repository layer providing clean persistence operations and query abstraction."""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from src.database.models import (
    ChurnPrediction,
    Customer,
    CustomerFeatures,
    DataQualityRejection,
    Order,
    OrderItem,
    PipelineRun,
    Product,
)

logger = logging.getLogger(__name__)


class DatabaseRepository:
    """Repository class encapsulating database operations."""

    def __init__(self, session: Session):
        self.session = session

    # --- Pipeline & Audit Operations ---

    def create_pipeline_run(self, batch_id: str, total_rows: int = 0) -> PipelineRun:
        """Initialize a new pipeline run audit record."""
        run = PipelineRun(
            batch_id=batch_id,
            start_time=datetime.now(),
            status="RUNNING",
            total_rows=total_rows,
        )
        self.session.add(run)
        self.session.flush()
        return run

    def update_pipeline_run(
        self,
        batch_id: str,
        status: str,
        accepted_rows: int,
        rejected_rows: int,
        duplicate_rows: int,
        missing_customer_rows: int,
        cancellation_rows: int,
        error_summary: Optional[str] = None,
    ) -> None:
        """Update audit record on batch completion or failure."""
        run = self.session.get(PipelineRun, batch_id)
        if run:
            run.end_time = datetime.now()
            run.status = status
            run.accepted_rows = accepted_rows
            run.rejected_rows = rejected_rows
            run.duplicate_rows = duplicate_rows
            run.missing_customer_rows = missing_customer_rows
            run.cancellation_rows = cancellation_rows
            run.error_summary = error_summary
            self.session.flush()

    def record_data_rejections(self, rejections: List[Dict[str, Any]]) -> None:
        """Bulk record rejected records."""
        if not rejections:
            return
        records = [
            DataQualityRejection(
                batch_id=r["batch_id"],
                row_number=r["row_number"],
                rejection_reason=r["rejection_reason"],
                raw_record=str(r["raw_record"]),
            )
            for r in rejections
        ]
        self.session.bulk_save_objects(records)
        self.session.flush()

    # --- Dimension Upserts ---

    def upsert_customers(self, customer_records: List[Dict[str, Any]]) -> None:
        """Idempotently insert or update customers."""
        for c in customer_records:
            cust = self.session.get(Customer, c["customer_id"])
            if cust:
                if c.get("country") and cust.country == "Unknown":
                    cust.country = c["country"]
                if c.get("order_date"):
                    od = c["order_date"]
                    if not cust.first_order_date or od < cust.first_order_date:
                        cust.first_order_date = od
                    if not cust.last_order_date or od > cust.last_order_date:
                        cust.last_order_date = od
                cust.total_orders += c.get("order_count_inc", 1)
            else:
                cust = Customer(
                    customer_id=c["customer_id"],
                    country=c.get("country", "Unknown"),
                    first_order_date=c.get("order_date"),
                    last_order_date=c.get("order_date"),
                    total_orders=c.get("order_count_inc", 1),
                )
                self.session.add(cust)
        self.session.flush()

    def upsert_products(self, product_records: List[Dict[str, Any]]) -> None:
        """Idempotently insert or update products."""
        for p in product_records:
            prod = self.session.get(Product, p["product_id"])
            if prod:
                if p.get("product_name") and prod.product_name in ("", "Unknown"):
                    prod.product_name = p["product_name"]
            else:
                prod = Product(
                    product_id=p["product_id"],
                    product_name=p.get("product_name", "Unknown Product"),
                    category=p.get("category", "General"),
                )
                self.session.add(prod)
        self.session.flush()

    # --- Orders and Line Items ---

    def insert_orders_and_items(
        self,
        orders_data: List[Dict[str, Any]],
        items_data: List[Dict[str, Any]],
    ) -> None:
        """Insert order headers and line items with conflict protection."""
        # 1. Insert Orders
        for o in orders_data:
            existing = self.session.get(Order, o["order_id"])
            if not existing:
                order = Order(
                    order_id=o["order_id"],
                    customer_id=o.get("customer_id"),
                    order_date=o["order_date"],
                    status=o["status"],
                    is_cancellation=o["is_cancellation"],
                    country=o.get("country", "Unknown"),
                    gross_amount=o.get("gross_amount", Decimal("0.00")),
                    discount_or_return_amount=o.get("discount_or_return_amount", Decimal("0.00")),
                    net_amount=o.get("net_amount", Decimal("0.00")),
                    batch_id=o.get("batch_id"),
                )
                self.session.add(order)
            else:
                # Update totals if order header was already created
                existing.gross_amount += o.get("gross_amount", Decimal("0.00"))
                existing.discount_or_return_amount += o.get("discount_or_return_amount", Decimal("0.00"))
                existing.net_amount += o.get("net_amount", Decimal("0.00"))

        self.session.flush()

        # 2. Insert Order Items safely (checking duplicate line hashes)
        existing_hashes = set(
            self.session.scalars(
                select(OrderItem.line_hash).where(
                    OrderItem.line_hash.in_([it["line_hash"] for it in items_data])
                )
            ).all()
        )

        new_items = []
        for it in items_data:
            if it["line_hash"] not in existing_hashes:
                new_items.append(
                    OrderItem(
                        order_id=it["order_id"],
                        product_id=it["product_id"],
                        quantity=it["quantity"],
                        unit_price=it["unit_price"],
                        line_total=it["line_total"],
                        line_hash=it["line_hash"],
                    )
                )
                existing_hashes.add(it["line_hash"])

        if new_items:
            self.session.bulk_save_objects(new_items)
            self.session.flush()

    # --- Feature Store & Predictions ---

    def save_customer_features(self, features: List[Dict[str, Any]]) -> None:
        """Persist computed RFM and behavioral feature vectors."""
        for f in features:
            stmt = select(CustomerFeatures).where(
                CustomerFeatures.customer_id == f["customer_id"],
                CustomerFeatures.snapshot_date == f["snapshot_date"],
            )
            existing = self.session.scalars(stmt).first()
            if existing:
                existing.recency_days = f["recency_days"]
                existing.frequency = f["frequency"]
                existing.monetary_value = f["monetary_value"]
                existing.average_order_value = f["average_order_value"]
                existing.purchase_interval_avg = f.get("purchase_interval_avg", Decimal("0.00"))
                existing.purchase_interval_std = f.get("purchase_interval_std", Decimal("0.00"))
                existing.return_rate = f.get("return_rate", Decimal("0.0000"))
            else:
                record = CustomerFeatures(
                    customer_id=f["customer_id"],
                    snapshot_date=f["snapshot_date"],
                    recency_days=f["recency_days"],
                    frequency=f["frequency"],
                    monetary_value=f["monetary_value"],
                    average_order_value=f["average_order_value"],
                    purchase_interval_avg=f.get("purchase_interval_avg", Decimal("0.00")),
                    purchase_interval_std=f.get("purchase_interval_std", Decimal("0.00")),
                    return_rate=f.get("return_rate", Decimal("0.0000")),
                )
                self.session.add(record)
        self.session.flush()

    def save_churn_predictions(self, predictions: List[Dict[str, Any]]) -> None:
        """Persist model inference predictions and risk segments."""
        for p in predictions:
            stmt = select(ChurnPrediction).where(
                ChurnPrediction.customer_id == p["customer_id"],
                ChurnPrediction.prediction_date == p["prediction_date"],
                ChurnPrediction.model_version == p["model_version"],
            )
            existing = self.session.scalars(stmt).first()
            if existing:
                existing.churn_probability = p["churn_probability"]
                existing.risk_segment = p["risk_segment"]
                existing.model_type = p["model_type"]
                existing.threshold_applied = p.get("threshold_applied", Decimal("0.5000"))
            else:
                pred = ChurnPrediction(
                    customer_id=p["customer_id"],
                    prediction_date=p["prediction_date"],
                    churn_probability=p["churn_probability"],
                    risk_segment=p["risk_segment"],
                    model_version=p["model_version"],
                    model_type=p["model_type"],
                    threshold_applied=p.get("threshold_applied", Decimal("0.5000")),
                )
                self.session.add(pred)
        self.session.flush()
