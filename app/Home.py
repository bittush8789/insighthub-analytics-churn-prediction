"""E-commerce Customer Analytics & Churn Prediction Platform - Home Portal."""

import sys
from pathlib import Path

# Add project root to Python path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import streamlit as st
from sqlalchemy import desc, select

from app.components.ui_helpers import apply_custom_theme, render_empty_state
from src.config.settings import get_settings
from src.data.ingestion import DataIngestionPipeline
from src.database.connection import check_db_connection, get_read_only_session
from src.database.models import PipelineRun

st.set_page_config(
    page_title="InsightHub | E-commerce Intelligence",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_custom_theme()

st.title("🛍️ E-commerce Customer Analytics & Churn Intelligence Platform")
st.markdown(
    "A modular, production-oriented analytics platform built to ingest raw sales transactions, "
    "analyze cross-sectional revenue, detect customer purchasing patterns, predict churn with supervised ML, "
    "and answer strategic business questions with Google Gemini GenAI."
)

st.markdown("---")

# 1. System Health & Infrastructure Status
st.subheader("🖥️ Platform Infrastructure & Connectivity Status")
col_s1, col_s2, col_s3 = st.columns(3)

settings = get_settings()
db_connected = check_db_connection()

with col_s1:
    if db_connected:
        db_type = "SQLite" if settings.DATABASE_URL.startswith("sqlite") else "PostgreSQL"
        st.success(f"✅ **{db_type} Database**: Connected & Operational")
    else:
        st.error("❌ **Database**: Disconnected / Offline")

with col_s2:
    if settings.GEMINI_API_KEY and settings.GEMINI_API_KEY != "your_gemini_api_key_here":
        st.success(f"✅ **Google Gemini API**: Configured (`{settings.GEMINI_MODEL}`)")
    else:
        st.warning("⚠️ **Google Gemini API**: Key Not Set in `.env`")

with col_s3:
    model_artifact = settings.ARTIFACTS_DIR / "models" / "churn_model_v1.0.0.joblib"
    if model_artifact.exists():
        st.success("✅ **Churn ML Model**: v1.0.0 Serialized & Ready")
    else:
        st.info("ℹ️ **Churn ML Model**: Pending Training (`scripts/train_model.py`)")

st.markdown("---")

# 2. Controlled Data Ingestion Workflow
st.subheader("📥 Transaction Data Ingestion & Quality Control")
st.markdown(
    "Upload raw transactional data (**CSV** or **Excel .xlsx/.xls**) following the "
    "UCI Online Retail II dataset schema (`Invoice`, `StockCode`, `Description`, `Quantity`, `InvoiceDate`, `Price`, `Customer ID`, `Country`)."
)

uploaded_file = st.file_uploader(
    "Choose a transaction dataset file to ingest",
    type=["csv", "xlsx", "xls"],
    help="Upload sales dataset. Pipeline will normalize columns, validate records, track quality, and insert idempotently.",
)

if uploaded_file is not None:
    if st.button("🚀 Ingest & Process Dataset", type="primary"):
        if not db_connected:
            st.error("Cannot proceed with ingestion: Database is currently disconnected.")
        else:
            with st.spinner("Executing Data Validation, Cleaning, Reconciliation, and Batch Ingestion..."):
                try:
                    pipeline = DataIngestionPipeline()
                    summary = pipeline.run(uploaded_file)
                    st.success(f"🎉 **Ingestion Successful!** Batch ID: `{summary.batch_id}`")

                    # Display Ingestion Audit Metrics
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Total Rows Processed", f"{summary.total_input_rows:,}")
                    c2.metric("Accepted Lines", f"{summary.accepted_rows:,}")
                    c3.metric("Rejected Lines", f"{summary.rejected_rows:,}")
                    c4.metric("Net Ingested Revenue", f"${float(summary.net_revenue):,.2f}")

                    if summary.rejection_reasons:
                        with st.expander("🔍 View Data Quality Rejection Audit Details", expanded=False):
                            st.write(summary.rejection_reasons)
                            if summary.errors:
                                st.write("**Sample Rejection Errors:**")
                                for err in summary.errors[:10]:
                                    st.write(f"- {err}")

                except Exception as exc:
                    st.error(f"❌ Ingestion Failed: {exc}")

st.markdown("---")

# 3. Recent Ingestion Audit History
st.subheader("📋 Ingestion Pipeline Audit Log")
if db_connected:
    try:
        with get_read_only_session() as session:
            runs = (
                session.scalars(
                    select(PipelineRun).order_by(desc(PipelineRun.start_time)).limit(5)
                )
                .all()
            )
            if runs:
                data = [
                    {
                        "Batch ID": r.batch_id,
                        "Start Time": r.start_time.strftime("%Y-%m-%d %H:%M:%S") if r.start_time else "",
                        "Status": r.status,
                        "Total Rows": f"{r.total_rows:,}",
                        "Accepted": f"{r.accepted_rows:,}",
                        "Rejected": f"{r.rejected_rows:,}",
                        "Duplicates": f"{r.duplicate_rows:,}",
                        "Missing Cust": f"{r.missing_customer_rows:,}",
                        "Cancellations": f"{r.cancellation_rows:,}",
                    }
                    for r in runs
                ]
                st.dataframe(pd.DataFrame(data), use_container_width=True)
            else:
                render_empty_state(
                    "No Ingestion History Found",
                    "No batches have been ingested into PostgreSQL yet.",
                    "Upload a dataset using the uploader above or run `python scripts/ingest_data.py`.",
                )
    except Exception as exc:
        st.warning(f"Unable to read audit logs: {exc}")
else:
    render_empty_state("Database Disconnected", "Audit history is unavailable while database is offline.")
