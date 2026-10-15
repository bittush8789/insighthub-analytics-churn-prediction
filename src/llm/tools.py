"""Authorized analytical tools with strict parameter validation and read-only execution."""

import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy import desc, select

from src.analytics.aggregations import AnalyticsService
from src.config.settings import get_settings
from src.database.connection import get_read_only_session
from src.database.models import ChurnPrediction, CustomerFeatures
from src.utils.exceptions import SecurityViolationError

logger = logging.getLogger(__name__)

# Security: Allowed countries pattern to prevent injection
COUNTRY_PATTERN = re.compile(r"^[A-Za-z0-9\s\-',.]{1,50}$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_date_param(param_name: str, val: Optional[str]) -> Optional[date]:
    """Validate and sanitize YYYY-MM-DD date parameter."""
    if not val:
        return None
    val_str = str(val).strip()
    if not DATE_PATTERN.match(val_str):
        raise SecurityViolationError(f"Invalid date format for '{param_name}': '{val}'. Expected format: YYYY-MM-DD.")
    try:
        return datetime.strptime(val_str, "%Y-%m-%d").date()
    except ValueError as exc:
        raise SecurityViolationError(f"Invalid calendar date for '{param_name}': '{val}'.") from exc


def validate_country_param(country: Optional[str]) -> Optional[str]:
    """Validate and sanitize country string."""
    if not country or country.strip() in ("", "All"):
        return None
    c_str = country.strip()
    if not COUNTRY_PATTERN.match(c_str):
        raise SecurityViolationError(f"Disallowed country input: '{c_str}'.")
    return c_str


def validate_limit(limit: Any, default: int = 10, max_limit: int = 50) -> int:
    """Clamp integer limit to safe bounds."""
    try:
        val = int(limit)
        return max(1, min(val, max_limit))
    except (ValueError, TypeError):
        return default


# --- Approved Analytical Tools ---

def get_revenue_summary(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    country: Optional[str] = None,
) -> Dict[str, Any]:
    """Retrieve overall revenue KPIs: Gross Sales, Returns, Net Revenue, Orders, and AOV.

    Args:
        start_date: Optional start date in YYYY-MM-DD format.
        end_date: Optional end date in YYYY-MM-DD format.
        country: Optional country name filter (e.g., 'United Kingdom', 'Germany').
    """
    s_date = validate_date_param("start_date", start_date)
    e_date = validate_date_param("end_date", end_date)
    c_filter = validate_country_param(country)

    if s_date and e_date and s_date > e_date:
        raise SecurityViolationError("start_date cannot be later than end_date.")

    logger.info("Tool called: get_revenue_summary(start=%s, end=%s, country=%s)", s_date, e_date, c_filter)
    kpis = AnalyticsService.get_executive_kpis(start_date=s_date, end_date=e_date, country=c_filter)
    return {
        "period": f"{start_date or 'Earliest'} to {end_date or 'Latest'}",
        "country": country or "All",
        "gross_sales": f"${kpis['gross_sales']:,.2f}",
        "returns_amount": f"${kpis['returns_amount']:,.2f}",
        "net_revenue": f"${kpis['net_revenue']:,.2f}",
        "completed_orders": kpis["completed_orders"],
        "unique_customers": kpis["unique_customers"],
        "average_order_value": f"${kpis['average_order_value']:,.2f}",
        "repeat_purchase_rate": f"{kpis['repeat_purchase_rate']:.1f}%",
    }


def get_revenue_by_country(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Retrieve breakdown of Net Revenue and order count by country.

    Args:
        start_date: Optional start date in YYYY-MM-DD format.
        end_date: Optional end date in YYYY-MM-DD format.
        limit: Number of top countries to return (max 30).
    """
    s_date = validate_date_param("start_date", start_date)
    e_date = validate_date_param("end_date", end_date)
    safe_limit = validate_limit(limit, default=10, max_limit=30)

    logger.info("Tool called: get_revenue_by_country(limit=%d)", safe_limit)
    df = AnalyticsService.get_revenue_by_country(start_date=s_date, end_date=e_date, limit=safe_limit)
    if df.empty:
        return []

    return [
        {
            "country": r["country"],
            "net_revenue": f"${r['net_revenue']:,.2f}",
            "order_count": r["order_count"],
            "customer_count": r["customer_count"],
        }
        for _, r in df.iterrows()
    ]


def get_top_products(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 10,
    country: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieve top-performing products ranked by Net Revenue.

    Args:
        start_date: Optional start date in YYYY-MM-DD format.
        end_date: Optional end date in YYYY-MM-DD format.
        limit: Number of products to return (max 30).
        country: Optional country filter.
    """
    s_date = validate_date_param("start_date", start_date)
    e_date = validate_date_param("end_date", end_date)
    safe_limit = validate_limit(limit, default=10, max_limit=30)
    c_filter = validate_country_param(country)

    logger.info("Tool called: get_top_products(limit=%d, country=%s)", safe_limit, c_filter)
    df = AnalyticsService.get_top_products(start_date=s_date, end_date=e_date, limit=safe_limit, country=c_filter)
    if df.empty:
        return []

    return [
        {
            "product_id": r["product_id"],
            "product_name": r["product_name"],
            "total_units_sold": r["total_units"],
            "net_revenue": f"${r['net_revenue']:,.2f}",
        }
        for _, r in df.iterrows()
    ]


def get_monthly_revenue(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    country: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieve monthly chronological revenue trend (Net Revenue, Gross Sales, Returns).

    Args:
        start_date: Optional start date in YYYY-MM-DD format.
        end_date: Optional end date in YYYY-MM-DD format.
        country: Optional country filter.
    """
    s_date = validate_date_param("start_date", start_date)
    e_date = validate_date_param("end_date", end_date)
    c_filter = validate_country_param(country)

    logger.info("Tool called: get_monthly_revenue(country=%s)", c_filter)
    df = AnalyticsService.get_revenue_trends(start_date=s_date, end_date=e_date, interval="monthly", country=c_filter)
    if df.empty:
        return []

    return [
        {
            "month": r["period"],
            "gross_sales": f"${r['gross_sales']:,.2f}",
            "returns": f"${r['returns_amount']:,.2f}",
            "net_revenue": f"${r['net_revenue']:,.2f}",
            "order_count": r["order_count"],
        }
        for _, r in df.iterrows()
    ]


def get_customer_metrics() -> Dict[str, Any]:
    """Retrieve aggregate customer behavior metrics: Recency, Frequency, and Monetary distribution."""
    logger.info("Tool called: get_customer_metrics()")
    df = AnalyticsService.get_customer_distributions()
    if df.empty:
        return {"status": "No customer data available in database."}

    return {
        "total_active_customers": len(df),
        "average_customer_spend": f"${df['monetary_value'].mean():,.2f}",
        "median_customer_spend": f"${df['monetary_value'].median():,.2f}",
        "average_frequency": f"{df['frequency'].mean():.1f} orders",
        "average_recency_days": f"{df['recency_days'].mean():.1f} days",
        "median_recency_days": f"{df['recency_days'].median():.0f} days",
    }


def get_high_risk_customers(
    limit: int = 10,
    min_monetary_value: float = 0.0,
) -> List[Dict[str, Any]]:
    """Retrieve high-value customers predicted to have High Churn Risk.

    Args:
        limit: Number of customer records to retrieve (max 25).
        min_monetary_value: Minimum historical customer spending filter.
    """
    safe_limit = validate_limit(limit, default=10, max_limit=25)
    logger.info("Tool called: get_high_risk_customers(limit=%d, min_spend=%.2f)", safe_limit, min_monetary_value)

    with get_read_only_session() as session:
        query = (
            select(
                ChurnPrediction.customer_id,
                ChurnPrediction.churn_probability,
                ChurnPrediction.risk_segment,
                CustomerFeatures.monetary_value,
                CustomerFeatures.recency_days,
                CustomerFeatures.frequency,
            )
            .join(
                CustomerFeatures,
                ChurnPrediction.customer_id == CustomerFeatures.customer_id,
            )
            .where(
                ChurnPrediction.risk_segment == "High Risk",
                CustomerFeatures.monetary_value >= min_monetary_value,
            )
            .order_by(desc(CustomerFeatures.monetary_value))
            .limit(safe_limit)
        )

        rows = session.execute(query).fetchall()
        if not rows:
            return [{"status": "No high-risk customers found matching criteria."}]

        return [
            {
                "customer_id": f"CUST-{r.customer_id}",
                "churn_probability": f"{float(r.churn_probability) * 100:.1f}%",
                "risk_segment": r.risk_segment,
                "historical_spend": f"${float(r.monetary_value):,.2f}",
                "recency_days": r.recency_days,
                "order_frequency": r.frequency,
            }
            for r in rows
        ]


def get_model_evaluation_summary(model_version: str = "v1.0.0") -> Dict[str, Any]:
    """Retrieve official performance metrics and validation results of the churn prediction model.

    Args:
        model_version: Registered model version identifier (default: 'v1.0.0').
    """
    logger.info("Tool called: get_model_evaluation_summary(version=%s)", model_version)
    settings = get_settings()
    meta_path = settings.ARTIFACTS_DIR / "models" / f"churn_model_{model_version}_metadata.json"

    if not meta_path.exists():
        return {
            "status": "Model not yet trained",
            "message": f"No model artifact found for version '{model_version}'. Model must be trained via scripts/train_model.py.",
        }

    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        test_metrics = data.get("test_metrics", {})
        baseline_metrics = data.get("baseline_metrics", {})

        return {
            "model_version": data.get("model_version"),
            "model_type": data.get("model_type"),
            "decision_threshold": data.get("decision_threshold"),
            "test_roc_auc": test_metrics.get("roc_auc"),
            "test_pr_auc": test_metrics.get("pr_auc"),
            "test_f1_score": test_metrics.get("f1_score"),
            "test_recall": test_metrics.get("recall"),
            "test_precision": test_metrics.get("precision"),
            "baseline_pr_auc": baseline_metrics.get("pr_auc"),
            "trade_off_analysis": test_metrics.get("trade_off_analysis"),
        }
    except Exception as exc:
        logger.error("Failed to read model metadata: %s", exc)
        return {"error": f"Failed reading metadata: {exc}"}


# Registry of approved tools
APPROVED_TOOLS_MAP = {
    "get_revenue_summary": get_revenue_summary,
    "get_revenue_by_country": get_revenue_by_country,
    "get_top_products": get_top_products,
    "get_monthly_revenue": get_monthly_revenue,
    "get_customer_metrics": get_customer_metrics,
    "get_high_risk_customers": get_high_risk_customers,
    "get_model_evaluation_summary": get_model_evaluation_summary,
}

ALL_APPROVED_TOOL_FUNCTIONS = list(APPROVED_TOOLS_MAP.values())
