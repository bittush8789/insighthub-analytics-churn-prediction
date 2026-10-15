"""Unit tests for analytics calculations and KPI definitions."""

from decimal import Decimal
import pytest

from src.analytics.kpis import (
    compute_average_order_value,
    compute_net_revenue,
    compute_repeat_purchase_rate,
    compute_revenue_contribution,
)


def test_net_revenue_formula():
    """Verify Net Revenue equals Gross Sales minus Returns."""
    gross = Decimal("1000.50")
    returns = Decimal("150.25")
    net = compute_net_revenue(gross, returns)
    assert net == Decimal("850.25")


def test_average_order_value_formula():
    """Verify AOV calculation and division by zero guard."""
    assert compute_average_order_value(Decimal("500.00"), 5) == Decimal("100.00")
    assert compute_average_order_value(Decimal("0.00"), 0) == Decimal("0.00")
    assert compute_average_order_value(Decimal("100.00"), -1) == Decimal("0.00")


def test_repeat_purchase_rate_formula():
    """Verify Repeat Purchase Rate calculation."""
    # 25 repeat out of 100 total customers = 25.0%
    assert compute_repeat_purchase_rate(100, 25) == 25.0
    # Zero customers guard
    assert compute_repeat_purchase_rate(0, 0) == 0.0


def test_revenue_contribution_formula():
    """Verify customer revenue percentage contribution."""
    # $250 out of $1,000 = 25.0%
    assert compute_revenue_contribution(250.0, 1000.0) == 25.0
    # Total revenue zero guard
    assert compute_revenue_contribution(100.0, 0.0) == 0.0
