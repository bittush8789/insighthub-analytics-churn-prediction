"""Customer Analytics and RFM Behavioral Segmentation Page."""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import numpy as np
import pandas as pd
import streamlit as st

from app.components.charts import plot_rfm_histograms
from app.components.kpi_cards import render_kpi_card
from app.components.ui_helpers import apply_custom_theme, render_empty_state, render_error_banner
from src.analytics.aggregations import AnalyticsService
from src.analytics.kpis import compute_repeat_purchase_rate
from src.database.connection import check_db_connection

st.set_page_config(page_title="Customer Analytics | InsightHub", page_icon="👥", layout="wide")
apply_custom_theme()

st.title("👥 Customer Behavioral & RFM Analytics")
st.markdown("Understand purchasing intervals, recency decay, customer lifetime value, and behavioral segments.")

if not check_db_connection():
    render_empty_state("Database Offline", "Unable to connect to PostgreSQL.")
    st.stop()


def segment_customer(r_score: int, f_score: int, m_score: int) -> str:
    """Rule-based RFM segment categorization."""
    if r_score >= 4 and f_score >= 4:
        return "Champions"
    elif f_score >= 3 and m_score >= 3:
        return "Loyal Customers"
    elif r_score >= 3 and f_score <= 2:
        return "Recent Customers"
    elif r_score <= 2 and f_score >= 3:
        return "At Risk"
    else:
        return "Hibernating"


try:
    df_cust = AnalyticsService.get_customer_distributions()

    if df_cust.empty:
        render_empty_state(
            "No Customer Data Found",
            "Customer transaction history is not yet populated.",
            "Please ingest the retail dataset to view customer metrics.",
        )
        st.stop()

    # 1. Summary Metrics
    total_cust = len(df_cust)
    repeat_cust = int((df_cust["frequency"] > 1).sum())
    repeat_rate = compute_repeat_purchase_rate(total_cust, repeat_cust)
    total_rev = df_cust["monetary_value"].sum()

    col1, col2, col3, col4 = st.columns(4)
    render_kpi_card("Active Customer Base", f"{total_cust:,}", subtitle="Non-null customer IDs", col=col1)
    render_kpi_card("Repeat Purchase Rate", f"{repeat_rate:.1f}%", subtitle=f"{repeat_cust:,} returning buyers", col=col2)
    render_kpi_card("Avg Customer Lifetime Spend", f"${df_cust['monetary_value'].mean():,.2f}", subtitle="Across full history", col=col3)
    render_kpi_card("Median Recency", f"{df_cust['recency_days'].median():.0f} days", subtitle="Time since last order", col=col4)

    st.markdown("---")

    # 2. RFM Metric Distributions
    st.subheader("📊 Recency, Frequency & Monetary Distributions")
    fig_r, fig_f, fig_m = plot_rfm_histograms(df_cust)

    c_r, c_f, c_m = st.columns(3)
    with c_r:
        st.plotly_chart(fig_r, use_container_width=True)
    with c_f:
        st.plotly_chart(fig_f, use_container_width=True)
    with c_m:
        st.plotly_chart(fig_m, use_container_width=True)

    st.markdown("---")

    # 3. Rule-Based RFM Segmentation
    st.subheader("🏷️ Rule-Based RFM Behavioral Segments")

    # Compute quantiles safely (1 to 5)
    df_cust["r_score"] = pd.qcut(df_cust["recency_days"].rank(method="first"), q=5, labels=[5, 4, 3, 2, 1]).astype(int)
    df_cust["f_score"] = pd.qcut(df_cust["frequency"].rank(method="first"), q=5, labels=[1, 2, 3, 4, 5]).astype(int)
    df_cust["m_score"] = pd.qcut(df_cust["monetary_value"].rank(method="first"), q=5, labels=[1, 2, 3, 4, 5]).astype(int)

    df_cust["segment"] = df_cust.apply(lambda r: segment_customer(r["r_score"], r["f_score"], r["m_score"]), axis=1)

    seg_summary = (
        df_cust.groupby("segment")
        .agg(
            customer_count=("customer_id", "count"),
            avg_recency=("recency_days", "mean"),
            avg_frequency=("frequency", "mean"),
            total_net_spend=("monetary_value", "sum"),
            avg_net_spend=("monetary_value", "mean"),
        )
        .reset_index()
    )
    seg_summary["pct_customers"] = (seg_summary["customer_count"] / total_cust) * 100.0
    seg_summary["pct_revenue"] = (seg_summary["total_net_spend"] / total_rev) * 100.0 if total_rev > 0 else 0.0

    st.dataframe(
        seg_summary.style.format({
            "customer_count": "{:,}",
            "avg_recency": "{:.1f} days",
            "avg_frequency": "{:.1f} orders",
            "total_net_spend": "${:,.2f}",
            "avg_net_spend": "${:,.2f}",
            "pct_customers": "{:.1f}%",
            "pct_revenue": "{:.1f}%",
        }),
        use_container_width=True,
    )

    st.markdown("---")

    # 4. Top Customers by Revenue Contribution
    st.subheader("💎 Top Value Customers")
    top_cust = df_cust.sort_values("monetary_value", ascending=False).head(20).copy()
    top_cust["revenue_contribution"] = (top_cust["monetary_value"] / total_rev) * 100.0 if total_rev > 0 else 0.0

    st.dataframe(
        top_cust[["customer_id", "country", "monetary_value", "frequency", "recency_days", "segment", "revenue_contribution"]].style.format({
            "monetary_value": "${:,.2f}",
            "frequency": "{:,}",
            "recency_days": "{:,} days",
            "revenue_contribution": "{:.2f}%",
        }),
        use_container_width=True,
    )

except Exception as exc:
    render_error_banner(str(exc))
