"""Reusable KPI metric card components."""

from typing import Any, Dict, Optional
import streamlit as st


def render_kpi_card(
    label: str,
    value: Any,
    subtitle: Optional[str] = None,
    col=None,
) -> None:
    """Render a single modern styled metric card."""
    target = col if col is not None else st
    sub_html = f"<div class='kpi-subtitle'>{subtitle}</div>" if subtitle else ""
    target.markdown(
        f"""
        <div class="kpi-container">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            {sub_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_executive_kpis_row(kpis: Dict[str, Any]) -> None:
    """Render top row of executive KPIs."""
    col1, col2, col3, col4, col5 = st.columns(5)

    render_kpi_card(
        "Net Revenue",
        f"${kpis.get('net_revenue', 0.0):,.2f}",
        subtitle=f"Gross: ${kpis.get('gross_sales', 0.0):,.0f} | Ret: -${kpis.get('returns_amount', 0.0):,.0f}",
        col=col1,
    )
    render_kpi_card(
        "Completed Orders",
        f"{kpis.get('completed_orders', 0):,}",
        subtitle="Excludes cancellations",
        col=col2,
    )
    render_kpi_card(
        "Unique Customers",
        f"{kpis.get('unique_customers', 0):,}",
        subtitle="Non-null customer IDs",
        col=col3,
    )
    render_kpi_card(
        "Average Order Value",
        f"${kpis.get('average_order_value', 0.0):,.2f}",
        subtitle="Net Revenue / Orders",
        col=col4,
    )
    render_kpi_card(
        "Repeat Purchase Rate",
        f"{kpis.get('repeat_purchase_rate', 0.0):.1f}%",
        subtitle=f"{kpis.get('repeat_customers', 0):,} repeat customers",
        col=col5,
    )
