"""Parameterized analytics queries and aggregations executed via read-only sessions."""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
import pandas as pd
from sqlalchemy import case, desc, distinct, func, select, text

from src.analytics.kpis import (
    compute_average_order_value,
    compute_net_revenue,
    compute_repeat_purchase_rate,
)
from src.database.connection import get_read_only_session
from src.database.models import Customer, Order, OrderItem, Product
from src.utils.exceptions import AnalyticsError

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Service providing aggregated business metrics and reporting."""

    @staticmethod
    def get_executive_kpis(
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        country: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compute top-level business KPIs over a specified period and optional country filter."""
        try:
            with get_read_only_session() as session:
                query = select(
                    func.coalesce(func.sum(Order.gross_amount), 0).label("gross_sales"),
                    func.coalesce(func.sum(Order.discount_or_return_amount), 0).label("returns_amount"),
                    func.coalesce(func.sum(Order.net_amount), 0).label("net_revenue"),
                    func.count(distinct(case((Order.is_cancellation == False, Order.order_id), else_=None))).label("completed_orders"),
                    func.count(distinct(Order.customer_id)).label("unique_customers"),
                )

                if start_date:
                    query = query.where(Order.order_date >= datetime.combine(start_date, datetime.min.time()))
                if end_date:
                    query = query.where(Order.order_date <= datetime.combine(end_date, datetime.max.time()))
                if country and country != "All":
                    query = query.where(Order.country == country)

                row = session.execute(query).one()

                gross_sales = Decimal(str(row.gross_sales))
                returns_amount = Decimal(str(row.returns_amount))
                net_revenue = Decimal(str(row.net_revenue))
                completed_orders = int(row.completed_orders or 0)
                unique_customers = int(row.unique_customers or 0)

                aov = compute_average_order_value(net_revenue, completed_orders)

                # Repeat customer count
                repeat_query = (
                    select(func.count())
                    .select_from(
                        select(Order.customer_id)
                        .where(Order.customer_id.isnot(None), Order.is_cancellation == False)
                    )
                )
                if start_date:
                    repeat_query = select(func.count()).select_from(
                        select(Order.customer_id)
                        .where(
                            Order.customer_id.isnot(None),
                            Order.is_cancellation == False,
                            Order.order_date >= datetime.combine(start_date, datetime.min.time()),
                            Order.order_date <= datetime.combine(end_date or date.today(), datetime.max.time()),
                        )
                        .group_by(Order.customer_id)
                        .having(func.count(Order.order_id) > 1)
                        .subquery()
                    )
                else:
                    repeat_query = select(func.count()).select_from(
                        select(Order.customer_id)
                        .where(Order.customer_id.isnot(None), Order.is_cancellation == False)
                        .group_by(Order.customer_id)
                        .having(func.count(Order.order_id) > 1)
                        .subquery()
                    )

                repeat_customers = session.scalar(repeat_query) or 0
                repeat_rate = compute_repeat_purchase_rate(unique_customers, repeat_customers)

                return {
                    "gross_sales": float(gross_sales),
                    "returns_amount": float(returns_amount),
                    "net_revenue": float(net_revenue),
                    "completed_orders": completed_orders,
                    "unique_customers": unique_customers,
                    "average_order_value": float(aov),
                    "repeat_customers": repeat_customers,
                    "repeat_purchase_rate": repeat_rate,
                }
        except Exception as exc:
            logger.error("Failed to compute executive KPIs: %s", exc)
            raise AnalyticsError(f"Executive KPIs error: {exc}") from exc

    @staticmethod
    def get_revenue_by_country(
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 15,
    ) -> pd.DataFrame:
        """Aggregate revenue, order count, and customer count by country."""
        try:
            with get_read_only_session() as session:
                query = (
                    select(
                        Order.country,
                        func.coalesce(func.sum(Order.gross_amount), 0).label("gross_sales"),
                        func.coalesce(func.sum(Order.discount_or_return_amount), 0).label("returns_amount"),
                        func.coalesce(func.sum(Order.net_amount), 0).label("net_revenue"),
                        func.count(distinct(Order.order_id)).label("order_count"),
                        func.count(distinct(Order.customer_id)).label("customer_count"),
                    )
                    .group_by(Order.country)
                    .order_by(desc("net_revenue"))
                    .limit(limit)
                )

                if start_date:
                    query = query.where(Order.order_date >= datetime.combine(start_date, datetime.min.time()))
                if end_date:
                    query = query.where(Order.order_date <= datetime.combine(end_date, datetime.max.time()))

                results = session.execute(query).fetchall()
                data = [
                    {
                        "country": r.country,
                        "gross_sales": float(r.gross_sales),
                        "returns_amount": float(r.returns_amount),
                        "net_revenue": float(r.net_revenue),
                        "order_count": int(r.order_count),
                        "customer_count": int(r.customer_count),
                    }
                    for r in results
                ]
                return pd.DataFrame(data)
        except Exception as exc:
            logger.error("Failed to get revenue by country: %s", exc)
            raise AnalyticsError(f"Country revenue aggregation error: {exc}") from exc

    @staticmethod
    def get_top_products(
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 10,
        country: Optional[str] = None,
    ) -> pd.DataFrame:
        """Fetch top-performing products ranked by net revenue."""
        try:
            with get_read_only_session() as session:
                query = (
                    select(
                        OrderItem.product_id,
                        Product.product_name,
                        func.coalesce(func.sum(OrderItem.quantity), 0).label("total_units"),
                        func.coalesce(func.sum(OrderItem.line_total), 0).label("net_revenue"),
                    )
                    .join(Product, OrderItem.product_id == Product.product_id)
                    .join(Order, OrderItem.order_id == Order.order_id)
                    .group_by(OrderItem.product_id, Product.product_name)
                    .order_by(desc("net_revenue"))
                    .limit(limit)
                )

                if start_date:
                    query = query.where(Order.order_date >= datetime.combine(start_date, datetime.min.time()))
                if end_date:
                    query = query.where(Order.order_date <= datetime.combine(end_date, datetime.max.time()))
                if country and country != "All":
                    query = query.where(Order.country == country)

                results = session.execute(query).fetchall()
                data = [
                    {
                        "product_id": r.product_id,
                        "product_name": r.product_name,
                        "total_units": int(r.total_units),
                        "net_revenue": float(r.net_revenue),
                    }
                    for r in results
                ]
                return pd.DataFrame(data)
        except Exception as exc:
            logger.error("Failed to get top products: %s", exc)
            raise AnalyticsError(f"Top products query error: {exc}") from exc

    @staticmethod
    def get_revenue_trends(
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        interval: str = "monthly",
        country: Optional[str] = None,
    ) -> pd.DataFrame:
        """Fetch chronological revenue trends aggregated daily or monthly."""
        try:
            with get_read_only_session() as session:
                is_sqlite = session.bind.dialect.name == "sqlite"
                if is_sqlite:
                    fmt = "%Y-%m" if interval.lower() == "monthly" else "%Y-%m-%d"
                    trunc_date = func.strftime(fmt, Order.order_date).label("period")
                else:
                    date_trunc_unit = "month" if interval.lower() == "monthly" else "day"
                    trunc_date = func.date_trunc(date_trunc_unit, Order.order_date).label("period")

                query = (
                    select(
                        trunc_date,
                        func.coalesce(func.sum(Order.gross_amount), 0).label("gross_sales"),
                        func.coalesce(func.sum(Order.discount_or_return_amount), 0).label("returns_amount"),
                        func.coalesce(func.sum(Order.net_amount), 0).label("net_revenue"),
                        func.count(distinct(Order.order_id)).label("order_count"),
                    )
                    .group_by(trunc_date)
                    .order_by(trunc_date)
                )

                if start_date:
                    query = query.where(Order.order_date >= datetime.combine(start_date, datetime.min.time()))
                if end_date:
                    query = query.where(Order.order_date <= datetime.combine(end_date, datetime.max.time()))
                if country and country != "All":
                    query = query.where(Order.country == country)

                results = session.execute(query).fetchall()
                data = [
                    {
                        "period": str(r.period) if is_sqlite else pd.to_datetime(r.period).strftime("%Y-%m-%d" if date_trunc_unit == "day" else "%Y-%m"),
                        "gross_sales": float(r.gross_sales),
                        "returns_amount": float(r.returns_amount),
                        "net_revenue": float(r.net_revenue),
                        "order_count": int(r.order_count),
                    }
                    for r in results
                ]
                return pd.DataFrame(data)
        except Exception as exc:
            logger.error("Failed to get revenue trends: %s", exc)
            raise AnalyticsError(f"Revenue trends query error: {exc}") from exc

    @staticmethod
    def get_customer_distributions() -> pd.DataFrame:
        """Retrieve customer-level recency, frequency, and monetary metrics."""
        try:
            with get_read_only_session() as session:
                query = (
                    select(
                        Order.customer_id,
                        func.max(Order.country).label("country"),
                        func.count(distinct(Order.order_id)).label("frequency"),
                        func.coalesce(func.sum(Order.net_amount), 0).label("monetary_value"),
                        func.max(Order.order_date).label("last_purchase_date"),
                        func.min(Order.order_date).label("first_purchase_date"),
                    )
                    .where(Order.customer_id.isnot(None))
                    .group_by(Order.customer_id)
                )

                results = session.execute(query).fetchall()
                if not results:
                    return pd.DataFrame()

                # Derive recency relative to the max order date in dataset
                max_dt = max(r.last_purchase_date for r in results if r.last_purchase_date)

                data = []
                for r in results:
                    recency_days = (max_dt - r.last_purchase_date).days if r.last_purchase_date else 999
                    data.append({
                        "customer_id": r.customer_id,
                        "country": r.country,
                        "frequency": int(r.frequency),
                        "monetary_value": float(r.monetary_value),
                        "recency_days": max(recency_days, 0),
                        "last_purchase_date": r.last_purchase_date,
                    })

                return pd.DataFrame(data)
        except Exception as exc:
            logger.error("Failed to compute customer distributions: %s", exc)
            raise AnalyticsError(f"Customer distributions query error: {exc}") from exc
