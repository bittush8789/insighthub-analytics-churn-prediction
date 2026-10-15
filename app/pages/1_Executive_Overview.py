"""Executive Overview Dashboard Page."""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st

from app.components.charts import plot_revenue_trend
from app.components.filters import render_sidebar_filters
from app.components.kpi_cards import render_executive_kpis_row
from app.components.ui_helpers import apply_custom_theme, render_empty_state, render_error_banner
from src.analytics.aggregations import AnalyticsService
from src.database.connection import check_db_connection

st.set_page_config(page_title="Executive Overview | InsightHub", page_icon="📊", layout="wide")
apply_custom_theme()

st.title("📊 Executive Overview")
st.markdown("High-level executive metrics, revenue trends, and cross-period commercial performance.")

if not check_db_connection():
    render_empty_state(
        "Database Offline",
        "Unable to connect to PostgreSQL. Please verify your database connection in .env.",
    )
    st.stop()

# Sidebar Filters
start_date, end_date, country, _ = render_sidebar_filters(
    enable_country=True,
    enable_date_range=True,
    enable_limit=False,
    key_prefix="exec",
)

try:
    # 1. Executive KPIs
    kpis = AnalyticsService.get_executive_kpis(start_date=start_date, end_date=end_date, country=country)

    if kpis["completed_orders"] == 0:
        render_empty_state(
            "No Sales Data Available",
            "No completed orders match the selected filters or date range.",
            "Ingest transaction data or adjust filter controls.",
        )
        st.stop()

    render_executive_kpis_row(kpis)

    st.markdown("---")

    # 2. Chronological Revenue Trend
    st.subheader("📈 Chronological Sales & Returns Trajectory")
    trend_df = AnalyticsService.get_revenue_trends(
        start_date=start_date,
        end_date=end_date,
        interval="monthly",
        country=country,
    )

    if not trend_df.empty:
        fig_trend = plot_revenue_trend(trend_df)
        st.plotly_chart(fig_trend, use_container_width=True)

        # Tabular breakdown
        with st.expander("📄 View Monthly Financial Reconciliation Table", expanded=False):
            st.dataframe(trend_df, use_container_width=True)
    else:
        st.info("Insufficient period data to plot revenue trends.")

except Exception as exc:
    render_error_banner(str(exc))
