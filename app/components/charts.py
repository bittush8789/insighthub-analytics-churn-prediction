"""Reusable interactive Plotly chart components."""

from typing import Any, Dict, Tuple
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


# Consistent Plotly layout template
CHART_TEMPLATE = "plotly_dark"
COLOR_PRIMARY = "#3b82f6"
COLOR_SUCCESS = "#10b981"
COLOR_WARNING = "#f59e0b"
COLOR_DANGER = "#ef4444"


def plot_revenue_trend(df: pd.DataFrame) -> go.Figure:
    """Create interactive multi-metric revenue trend chart."""
    if df.empty:
        return go.Figure()

    fig = go.Figure()

    # Gross Sales line
    fig.add_trace(
        go.Scatter(
            x=df["period"],
            y=df["gross_sales"],
            mode="lines",
            name="Gross Sales",
            line=dict(color="#60a5fa", width=2, dash="dot"),
        )
    )

    # Returns line
    fig.add_trace(
        go.Scatter(
            x=df["period"],
            y=df["returns_amount"],
            mode="lines",
            name="Returns & Cancellations",
            line=dict(color=COLOR_DANGER, width=1.5),
        )
    )

    # Net Revenue filled area
    fig.add_trace(
        go.Scatter(
            x=df["period"],
            y=df["net_revenue"],
            mode="lines",
            name="Net Revenue",
            fill="tozeroy",
            fillcolor="rgba(59, 130, 246, 0.15)",
            line=dict(color=COLOR_PRIMARY, width=3),
        )
    )

    fig.update_layout(
        template=CHART_TEMPLATE,
        title="Chronological Revenue Trend (Gross Sales vs Returns vs Net Revenue)",
        xaxis_title="Time Period",
        yaxis_title="Amount ($)",
        hovermode="x unified",
        margin=dict(l=40, r=40, t=50, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def plot_country_revenue_bar(df: pd.DataFrame) -> go.Figure:
    """Create horizontal bar chart of revenue by country."""
    if df.empty:
        return go.Figure()

    sorted_df = df.sort_values("net_revenue", ascending=True)
    fig = px.bar(
        sorted_df,
        x="net_revenue",
        y="country",
        orientation="h",
        text_auto="$,.0f",
        title="Top Countries by Net Revenue",
        color="net_revenue",
        color_continuous_scale="Blues",
        template=CHART_TEMPLATE,
    )
    fig.update_layout(
        xaxis_title="Net Revenue ($)",
        yaxis_title="Country",
        margin=dict(l=40, r=40, t=50, b=40),
        coloraxis_showscale=False,
    )
    return fig


def plot_top_products_bar(df: pd.DataFrame) -> go.Figure:
    """Create horizontal bar chart of top products."""
    if df.empty:
        return go.Figure()

    sorted_df = df.sort_values("net_revenue", ascending=True).tail(15)
    # Truncate long descriptions
    sorted_df["short_name"] = sorted_df["product_name"].apply(lambda s: s[:30] + "..." if len(s) > 30 else s)

    fig = px.bar(
        sorted_df,
        x="net_revenue",
        y="short_name",
        orientation="h",
        text_auto="$,.0f",
        title="Top 15 Products by Net Revenue",
        color="net_revenue",
        color_continuous_scale="Tealgrn",
        template=CHART_TEMPLATE,
        hover_data=["product_id", "total_units", "net_revenue"],
    )
    fig.update_layout(
        xaxis_title="Net Revenue ($)",
        yaxis_title="Product",
        margin=dict(l=40, r=40, t=50, b=40),
        coloraxis_showscale=False,
    )
    return fig


def plot_rfm_histograms(df: pd.DataFrame) -> Tuple[go.Figure, go.Figure, go.Figure]:
    """Create individual histograms for Recency, Frequency, and Monetary distributions."""
    if df.empty:
        return go.Figure(), go.Figure(), go.Figure()

    # Recency
    fig_r = px.histogram(
        df,
        x="recency_days",
        nbins=30,
        title="Customer Recency Distribution (Days Since Last Order)",
        color_discrete_sequence=["#818cf8"],
        template=CHART_TEMPLATE,
    )
    fig_r.update_layout(xaxis_title="Recency (Days)", yaxis_title="Customer Count", margin=dict(l=30, r=30, t=40, b=30))

    # Frequency (log or clipped at 99th percentile for visual clarity)
    p99_freq = df["frequency"].quantile(0.99)
    filtered_freq = df[df["frequency"] <= p99_freq]
    fig_f = px.histogram(
        filtered_freq,
        x="frequency",
        nbins=25,
        title=f"Order Frequency Distribution (Clipped at 99th %ile: {int(p99_freq)})",
        color_discrete_sequence=["#34d399"],
        template=CHART_TEMPLATE,
    )
    fig_f.update_layout(xaxis_title="Completed Orders", yaxis_title="Customer Count", margin=dict(l=30, r=30, t=40, b=30))

    # Monetary Value
    p99_mon = df["monetary_value"].quantile(0.99)
    filtered_mon = df[(df["monetary_value"] > 0) & (df["monetary_value"] <= p99_mon)]
    fig_m = px.histogram(
        filtered_mon,
        x="monetary_value",
        nbins=30,
        title=f"Monetary Value Distribution (Clipped at 99th %ile: ${p99_mon:,.0f})",
        color_discrete_sequence=["#f472b6"],
        template=CHART_TEMPLATE,
    )
    fig_m.update_layout(xaxis_title="Total Net Spend ($)", yaxis_title="Customer Count", margin=dict(l=30, r=30, t=40, b=30))

    return fig_r, fig_f, fig_m


def plot_risk_segments_donut(df: pd.DataFrame) -> go.Figure:
    """Create donut chart showing customer distribution across risk segments."""
    if df.empty or "risk_segment" not in df.columns:
        return go.Figure()

    counts = df["risk_segment"].value_counts().reset_index()
    counts.columns = ["risk_segment", "customer_count"]

    color_map = {
        "High Risk": COLOR_DANGER,
        "Medium Risk": COLOR_WARNING,
        "Low Risk": COLOR_SUCCESS,
    }

    fig = px.pie(
        counts,
        values="customer_count",
        names="risk_segment",
        hole=0.55,
        title="Customer Churn Risk Breakdown",
        color="risk_segment",
        color_discrete_map=color_map,
        template=CHART_TEMPLATE,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(margin=dict(l=30, r=30, t=50, b=30))
    return fig


def plot_churn_probability_histogram(df: pd.DataFrame, threshold: float = 0.50) -> go.Figure:
    """Create histogram of predicted churn probabilities with threshold cutoff."""
    if df.empty or "churn_probability" not in df.columns:
        return go.Figure()

    fig = px.histogram(
        df,
        x="churn_probability",
        nbins=20,
        title="Predicted Churn Probability Distribution",
        color_discrete_sequence=["#a78bfa"],
        template=CHART_TEMPLATE,
    )
    fig.add_vline(
        x=threshold,
        line_width=2,
        line_dash="dash",
        line_color=COLOR_DANGER,
        annotation_text=f"Decision Cutoff ({threshold:.2f})",
        annotation_position="top right",
    )
    fig.update_layout(
        xaxis_title="Churn Probability (0.0 to 1.0)",
        yaxis_title="Customer Count",
        margin=dict(l=40, r=40, t=50, b=40),
    )
    return fig


def plot_confusion_matrix_heatmap(cm_dict: Dict[str, int]) -> go.Figure:
    """Create annotated confusion matrix heatmap."""
    z = [
        [cm_dict.get("true_negatives", 0), cm_dict.get("false_positives", 0)],
        [cm_dict.get("false_negatives", 0), cm_dict.get("true_positives", 0)],
    ]
    x = ["Predicted Retained (0)", "Predicted Churned (1)"]
    y = ["Actual Retained (0)", "Actual Churned (1)"]

    annotations = []
    for i, row in enumerate(z):
        for j, val in enumerate(row):
            annotations.append(
                dict(
                    x=x[j],
                    y=y[i],
                    text=f"<b>{val:,}</b>",
                    showarrow=False,
                    font=dict(color="white", size=16),
                )
            )

    fig = go.Figure(
        data=go.Heatmap(
            z=z,
            x=x,
            y=y,
            colorscale="Viridis",
            showscale=False,
        )
    )
    fig.update_layout(
        title="Model Confusion Matrix (Out-of-Time Test Set)",
        template=CHART_TEMPLATE,
        annotations=annotations,
        margin=dict(l=60, r=40, t=50, b=40),
        yaxis=dict(autorange="reversed"),
    )
    return fig
