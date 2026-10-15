"""Sales Analytics Page."""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st

from app.components.charts import (
    plot_country_revenue_bar,
    plot_revenue_trend,
    plot_top_products_bar,
)
from app.components.filters import render_sidebar_filters
from app.components.ui_helpers import apply_custom_theme, render_empty_state, render_error_banner
from src.analytics.aggregations import AnalyticsService
from src.database.connection import check_db_connection

st.set_page_config(page_title="Sales Analytics | InsightHub", page_icon="📈", layout="wide")
apply_custom_theme()

st.title("📈 Sales & Product Analytics")
st.markdown("Detailed breakdown of revenue generation across geographic markets, top SKUs, and time intervals.")

if not check_db_connection():
    render_empty_state("Database Offline", "Unable to connect to PostgreSQL.")
    st.stop()

# Sidebar Filters
start_date, end_date, country, limit = render_sidebar_filters(
    enable_country=True,
    enable_date_range=True,
    enable_limit=True,
    key_prefix="sales",
)

try:
    # 1. Geographic and Product Breakdown
    col_geo, col_prod = st.columns(2)

    with col_geo:
        st.subheader("🌍 Revenue by Country")
        country_df = AnalyticsService.get_revenue_by_country(
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
        if not country_df.empty:
            fig_country = plot_country_revenue_bar(country_df)
            st.plotly_chart(fig_country, use_container_width=True)
        else:
            st.info("No country sales data available.")

    with col_prod:
        st.subheader("🏆 Top Performing Products")
        product_df = AnalyticsService.get_top_products(
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            country=country,
        )
        if not product_df.empty:
            fig_prod = plot_top_products_bar(product_df)
            st.plotly_chart(fig_prod, use_container_width=True)
        else:
            st.info("No product sales data available.")

    st.markdown("---")

    # 2. Granular Revenue Trend (Daily vs Monthly)
    st.subheader("📅 Sales Dynamics & Periodic Velocity")
    trend_mode = st.radio("Trend Granularity", options=["Monthly", "Daily"], horizontal=True)

    trend_df = AnalyticsService.get_revenue_trends(
        start_date=start_date,
        end_date=end_date,
        interval=trend_mode.lower(),
        country=country,
    )

    if not trend_df.empty:
        fig_trend = plot_revenue_trend(trend_df)
        st.plotly_chart(fig_trend, use_container_width=True)
    else:
        st.info("No trend data available for selected criteria.")

except Exception as exc:
    render_error_banner(str(exc))
