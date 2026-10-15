"""Core KPI definitions and calculation logic.

KPI Definitions (applied uniformly across SQL, Dashboards, and GenAI):
1. Gross Sales: Sum of (quantity * unit_price) for all completed transactions (quantity > 0).
2. Returns and Cancellations: Absolute sum of (quantity * unit_price) for all cancelled transactions (is_cancellation = True or quantity < 0).
3. Net Revenue: Gross Sales - Returns and Cancellations.
4. Total Orders: Count of distinct order identifiers for completed purchases.
5. Unique Customers: Count of distinct non-null customer identifiers with at least one order.
6. Average Order Value (AOV): Net Revenue / Total Completed Orders (or Gross Sales / Completed Orders when strictly evaluating basket size).
7. Repeat Purchase Rate: Percentage of unique customers who placed more than 1 completed order: (Repeat Customers / Total Unique Customers) * 100.
8. Customer Recency: Days elapsed between the snapshot date (or current date) and the customer's most recent completed order.
9. Customer Purchase Frequency: Total number of qualifying orders placed by the customer within the lookback window.
10. Customer Monetary Value: Total net spending by the customer across all completed purchases.
11. Customer Revenue Contribution: Percentage of total business net revenue contributed by an individual or cohort of customers.
"""

from decimal import Decimal
from typing import Any, Dict, Optional
import numpy as np
import pandas as pd


def compute_net_revenue(gross_sales: Decimal, returns_amount: Decimal) -> Decimal:
    """Compute Net Revenue = Gross Sales - Returns and Cancellations."""
    return gross_sales - returns_amount


def compute_average_order_value(net_revenue: Decimal, completed_orders: int) -> Decimal:
    """Compute Average Order Value (AOV). Returns 0.00 if completed_orders is 0."""
    if completed_orders <= 0:
        return Decimal("0.00")
    return round(net_revenue / Decimal(completed_orders), 2)


def compute_repeat_purchase_rate(total_customers: int, repeat_customers: int) -> float:
    """Compute Repeat Purchase Rate as a percentage (0.0 to 100.0)."""
    if total_customers <= 0:
        return 0.0
    return round((repeat_customers / total_customers) * 100.0, 2)


def compute_revenue_contribution(customer_spending: float, total_business_revenue: float) -> float:
    """Compute individual customer or cohort contribution to total net revenue."""
    if total_business_revenue <= 0.0:
        return 0.0
    return round((customer_spending / total_business_revenue) * 100.0, 4)
