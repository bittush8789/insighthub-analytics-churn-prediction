"""SQLAlchemy declarative models for the E-commerce platform."""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy declarative entities."""
    pass


class PipelineRun(Base):
    """Tracks batch ingestion audit, data quality metrics, and execution status."""

    __tablename__ = "pipeline_runs"

    batch_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="RUNNING")  # RUNNING, COMPLETED, FAILED
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    accepted_rows: Mapped[int] = mapped_column(Integer, default=0)
    rejected_rows: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_rows: Mapped[int] = mapped_column(Integer, default=0)
    missing_customer_rows: Mapped[int] = mapped_column(Integer, default=0)
    cancellation_rows: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    rejections: Mapped[List["DataQualityRejection"]] = relationship("DataQualityRejection", back_populates="pipeline_run", cascade="all, delete-orphan")
    orders: Mapped[List["Order"]] = relationship("Order", back_populates="pipeline_run")


class DataQualityRejection(Base):
    """Stores rejected records during ingestion with detailed reasons."""

    __tablename__ = "data_quality_rejections"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(String(64), ForeignKey("pipeline_runs.batch_id", ondelete="CASCADE"), nullable=False, index=True)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    rejection_reason: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_record: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    pipeline_run: Mapped["PipelineRun"] = relationship("PipelineRun", back_populates="rejections")


class Customer(Base):
    """Customer dimension table."""

    __tablename__ = "customers"

    customer_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    country: Mapped[str] = mapped_column(String(100), nullable=False, default="Unknown", index=True)
    first_order_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_order_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    total_orders: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    orders: Mapped[List["Order"]] = relationship("Order", back_populates="customer")
    features: Mapped[List["CustomerFeatures"]] = relationship("CustomerFeatures", back_populates="customer", cascade="all, delete-orphan")
    predictions: Mapped[List["ChurnPrediction"]] = relationship("ChurnPrediction", back_populates="customer", cascade="all, delete-orphan")


class Product(Base):
    """Product dimension table."""

    __tablename__ = "products"

    product_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(100), default="General")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    order_items: Mapped[List["OrderItem"]] = relationship("OrderItem", back_populates="product")


class Order(Base):
    """Order transaction header table."""

    __tablename__ = "orders"

    order_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("customers.customer_id", ondelete="SET NULL"), nullable=True, index=True)
    order_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="COMPLETED", index=True)
    is_cancellation: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    country: Mapped[str] = mapped_column(String(100), nullable=False, default="Unknown", index=True)
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    discount_or_return_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    net_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    batch_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("pipeline_runs.batch_id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    customer: Mapped[Optional["Customer"]] = relationship("Customer", back_populates="orders")
    pipeline_run: Mapped[Optional["PipelineRun"]] = relationship("PipelineRun", back_populates="orders")
    items: Mapped[List["OrderItem"]] = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    """Order line item detail table."""

    __tablename__ = "order_items"

    item_id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(64), ForeignKey("orders.order_id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(String(64), ForeignKey("products.product_id", ondelete="RESTRICT"), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    line_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    order: Mapped["Order"] = relationship("Order", back_populates="items")
    product: Mapped["Product"] = relationship("Product", back_populates="order_items")


class CustomerFeatures(Base):
    """Point-in-time RFM and behavioral metrics for churn modeling."""

    __tablename__ = "customer_features"
    __table_args__ = (
        UniqueConstraint("customer_id", "snapshot_date", name="uq_customer_snapshot"),
        Index("idx_cf_customer_snapshot", "customer_id", "snapshot_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    customer_id: Mapped[str] = mapped_column(String(64), ForeignKey("customers.customer_id", ondelete="CASCADE"), nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    recency_days: Mapped[int] = mapped_column(Integer, nullable=False)
    frequency: Mapped[int] = mapped_column(Integer, nullable=False)
    monetary_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    average_order_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    purchase_interval_avg: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    purchase_interval_std: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    return_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.0000"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    customer: Mapped["Customer"] = relationship("Customer", back_populates="features")


class ChurnPrediction(Base):
    """Customer-level churn risk probabilities and segments."""

    __tablename__ = "churn_predictions"
    __table_args__ = (
        UniqueConstraint("customer_id", "prediction_date", "model_version", name="uq_customer_prediction"),
        Index("idx_cp_risk_segment", "risk_segment"),
        Index("idx_cp_churn_prob", "churn_probability"),
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    customer_id: Mapped[str] = mapped_column(String(64), ForeignKey("customers.customer_id", ondelete="CASCADE"), nullable=False, index=True)
    prediction_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    churn_probability: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    risk_segment: Mapped[str] = mapped_column(String(32), nullable=False)  # 'Low Risk', 'Medium Risk', 'High Risk'
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model_type: Mapped[str] = mapped_column(String(64), nullable=False)
    threshold_applied: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.5000"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    customer: Mapped["Customer"] = relationship("Customer", back_populates="predictions")
