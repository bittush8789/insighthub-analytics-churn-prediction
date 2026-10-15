"""Analytics module."""

from src.analytics.aggregations import AnalyticsService
from src.analytics.kpis import (
    compute_average_order_value,
    compute_net_revenue,
    compute_repeat_purchase_rate,
    compute_revenue_contribution,
)

__all__ = [
    "AnalyticsService",
    "compute_net_revenue",
    "compute_average_order_value",
    "compute_repeat_purchase_rate",
    "compute_revenue_contribution",
]
