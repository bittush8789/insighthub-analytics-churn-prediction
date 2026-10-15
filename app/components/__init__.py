"""Streamlit components package."""

from app.components.charts import (
    plot_churn_probability_histogram,
    plot_confusion_matrix_heatmap,
    plot_country_revenue_bar,
    plot_revenue_trend,
    plot_rfm_histograms,
    plot_risk_segments_donut,
    plot_top_products_bar,
)
from app.components.filters import render_sidebar_filters
from app.components.kpi_cards import render_executive_kpis_row, render_kpi_card
from app.components.ui_helpers import (
    apply_custom_theme,
    render_empty_state,
    render_error_banner,
)

__all__ = [
    "apply_custom_theme",
    "render_empty_state",
    "render_error_banner",
    "render_kpi_card",
    "render_executive_kpis_row",
    "plot_revenue_trend",
    "plot_country_revenue_bar",
    "plot_top_products_bar",
    "plot_rfm_histograms",
    "plot_risk_segments_donut",
    "plot_churn_probability_histogram",
    "plot_confusion_matrix_heatmap",
    "render_sidebar_filters",
]
