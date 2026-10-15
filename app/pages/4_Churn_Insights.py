"""Churn Insights and Machine Learning Risk Scoring Page."""

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import streamlit as st
from sqlalchemy import desc, select

from app.components.charts import (
    plot_churn_probability_histogram,
    plot_confusion_matrix_heatmap,
    plot_risk_segments_donut,
)
from app.components.kpi_cards import render_kpi_card
from app.components.ui_helpers import apply_custom_theme, render_empty_state, render_error_banner
from src.config.settings import get_settings
from src.database.connection import check_db_connection, get_read_only_session
from src.database.models import ChurnPrediction, Customer, CustomerFeatures

st.set_page_config(page_title="Churn Insights | InsightHub", page_icon="🔮", layout="wide")
apply_custom_theme()

st.title("🔮 Predictive Churn Risk & Retention Intelligence")
st.markdown(
    "Supervised machine learning predictions identifying customer attrition risk over a 90-day forward horizon. "
    "Features are calculated point-in-time strictly prior to observation, avoiding temporal data leakage."
)

st.info(
    "💡 **Distinction Between Predictions & Observations**: "
    "**Predictions** represent statistical probabilities produced by the trained model indicating the likelihood "
    "that a customer will make zero qualifying purchases in the next 90 days. "
    "They are not deterministic facts or certainties, and proactive retention actions may alter outcomes."
)

if not check_db_connection():
    render_empty_state("Database Offline", "Unable to connect to PostgreSQL.")
    st.stop()

settings = get_settings()

try:
    # 1. Query persisted churn predictions joined with customer features
    with get_read_only_session() as session:
        query = (
            select(
                ChurnPrediction.customer_id,
                Customer.country,
                ChurnPrediction.churn_probability,
                ChurnPrediction.risk_segment,
                ChurnPrediction.model_version,
                ChurnPrediction.model_type,
                ChurnPrediction.threshold_applied,
                CustomerFeatures.monetary_value,
                CustomerFeatures.recency_days,
                CustomerFeatures.frequency,
            )
            .join(Customer, ChurnPrediction.customer_id == Customer.customer_id)
            .outerjoin(CustomerFeatures, ChurnPrediction.customer_id == CustomerFeatures.customer_id)
            .order_by(desc(ChurnPrediction.churn_probability))
        )
        rows = session.execute(query).fetchall()

    if not rows:
        render_empty_state(
            "No Churn Predictions Found",
            "No customer churn predictions have been persisted to PostgreSQL yet.",
            "Please train the model and generate inference predictions using:\n"
            "`python scripts/train_model.py` and `python scripts/generate_predictions.py`.",
        )

        # Still render model evaluation card if artifact is present
        meta_path = settings.ARTIFACTS_DIR / "models" / "churn_model_v1.0.0_metadata.json"
        if meta_path.exists():
            st.markdown("---")
            st.subheader("📋 Model Evaluation Artifact Summary")
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            st.json(meta)
        st.stop()

    df_preds = pd.DataFrame([
        {
            "customer_id": r.customer_id,
            "country": r.country,
            "churn_probability": float(r.churn_probability),
            "risk_segment": r.risk_segment,
            "monetary_value": float(r.monetary_value or 0.0),
            "recency_days": int(r.recency_days or 0),
            "frequency": int(r.frequency or 0),
            "model_version": r.model_version,
            "model_type": r.model_type,
            "threshold": float(r.threshold_applied or 0.5),
        }
        for r in rows
    ])

    # 2. Risk Overview KPI Cards
    total_scored = len(df_preds)
    high_risk_count = int((df_preds["risk_segment"] == "High Risk").sum())
    med_risk_count = int((df_preds["risk_segment"] == "Medium Risk").sum())
    high_risk_rev = df_preds[df_preds["risk_segment"] == "High Risk"]["monetary_value"].sum()

    col1, col2, col3, col4 = st.columns(4)
    render_kpi_card("Total Customers Scored", f"{total_scored:,}", subtitle=f"Model {df_preds['model_version'].iloc[0]}", col=col1)
    render_kpi_card("High Risk Customers", f"{high_risk_count:,}", subtitle=f"{(high_risk_count / total_scored) * 100:.1f}% of cohort", col=col2)
    render_kpi_card("Medium Risk Customers", f"{med_risk_count:,}", subtitle=f"{(med_risk_count / total_scored) * 100:.1f}% of cohort", col=col3)
    render_kpi_card("Revenue at High Risk", f"${high_risk_rev:,.2f}", subtitle="Total lifetime spend of high risk group", col=col4)

    st.markdown("---")

    # 3. Probability Distribution & Risk Breakdown
    c_dist, c_pie = st.columns(2)
    threshold = df_preds["threshold"].iloc[0] if not df_preds.empty else 0.50

    with c_dist:
        st.plotly_chart(plot_churn_probability_histogram(df_preds, threshold=threshold), use_container_width=True)

    with c_pie:
        st.plotly_chart(plot_risk_segments_donut(df_preds), use_container_width=True)

    st.markdown("---")

    # 4. Interactive Customer Risk Explorer
    st.subheader("🔎 Customer Risk Explorer & Retention Targets")

    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        risk_filter = st.multiselect(
            "Filter by Risk Segment",
            options=["High Risk", "Medium Risk", "Low Risk"],
            default=["High Risk"],
        )
    with col_f2:
        countries = ["All"] + sorted(list(df_preds["country"].unique()))
        country_filter = st.selectbox("Filter by Country", options=countries, index=0)
    with col_f3:
        min_spend = st.number_input("Minimum Historical Spend ($)", min_value=0, value=100, step=100)

    filtered_df = df_preds.copy()
    if risk_filter:
        filtered_df = filtered_df[filtered_df["risk_segment"].in_(risk_filter)]
    if country_filter != "All":
        filtered_df = filtered_df[filtered_df["country"] == country_filter]
    filtered_df = filtered_df[filtered_df["monetary_value"] >= min_spend]

    st.write(f"Showing **{len(filtered_df):,}** customers matching criteria:")

    st.dataframe(
        filtered_df[[
            "customer_id",
            "country",
            "risk_segment",
            "churn_probability",
            "monetary_value",
            "recency_days",
            "frequency",
        ]]
        .sort_values(["churn_probability", "monetary_value"], ascending=[False, False])
        .head(100)
        .style.format({
            "churn_probability": "{:.1%}",
            "monetary_value": "${:,.2f}",
            "recency_days": "{:,} days",
            "frequency": "{:,} orders",
        }),
        use_container_width=True,
    )

    st.markdown("---")

    # 5. Model Evaluation and Diagnostic Summary
    st.subheader("📊 Model Validation & Performance Summary")
    meta_path = settings.ARTIFACTS_DIR / "models" / f"churn_model_{df_preds['model_version'].iloc[0]}_metadata.json"

    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        test_metrics = metadata.get("test_metrics", {})
        baseline_metrics = metadata.get("baseline_metrics", {})

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Test ROC-AUC", f"{test_metrics.get('roc_auc', 0.0):.3f}", delta=f"{test_metrics.get('roc_auc', 0.0) - baseline_metrics.get('roc_auc', 0.0):+.3f} vs baseline")
        m2.metric("Test PR-AUC", f"{test_metrics.get('pr_auc', 0.0):.3f}", delta=f"{test_metrics.get('pr_auc', 0.0) - baseline_metrics.get('pr_auc', 0.0):+.3f} vs baseline")
        m3.metric("F1-Score", f"{test_metrics.get('f1_score', 0.0):.3f}")
        m4.metric("Recall", f"{test_metrics.get('recall', 0.0):.3f}")
        m5.metric("Precision", f"{test_metrics.get('precision', 0.0):.3f}")

        st.caption(f"**Business Trade-off Analysis**: {test_metrics.get('trade_off_analysis', 'N/A')}")

        if "confusion_matrix" in test_metrics:
            fig_cm = plot_confusion_matrix_heatmap(test_metrics["confusion_matrix"])
            st.plotly_chart(fig_cm, use_container_width=True)

except Exception as exc:
    render_error_banner(str(exc))
