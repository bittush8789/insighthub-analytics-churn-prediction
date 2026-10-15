"""Sidebar filter widgets and selectors."""

from datetime import date, timedelta
from typing import List, Optional, Tuple
import streamlit as st
from sqlalchemy import distinct, select

from src.database.connection import check_db_connection, get_read_only_session
from src.database.models import Order


def get_available_countries() -> List[str]:
    """Fetch distinct countries from orders table."""
    if not check_db_connection():
        return ["All"]

    try:
        with get_read_only_session() as session:
            rows = session.scalars(select(distinct(Order.country)).order_by(Order.country)).all()
            valid = [r for r in rows if r and r.strip() != ""]
            return ["All"] + valid
    except Exception:
        return ["All"]


def render_sidebar_filters(
    enable_country: bool = True,
    enable_date_range: bool = True,
    enable_limit: bool = False,
    key_prefix: str = "filter",
) -> Tuple[Optional[date], Optional[date], Optional[str], int]:
    """Render standardized dashboard sidebar filters.

    Returns:
        Tuple of (start_date, end_date, selected_country, limit)
    """
    st.sidebar.markdown("### 🎛️ Filter Controls")

    start_date: Optional[date] = None
    end_date: Optional[date] = None
    selected_country: Optional[str] = None
    limit: int = 10

    if enable_date_range:
        st.sidebar.markdown("**Date Range**")
        col_d1, col_d2 = st.sidebar.columns(2)
        # Default to a broad range or custom input
        start_date = col_d1.date_input("From", value=None, key=f"{key_prefix}_start_date")
        end_date = col_d2.date_input("To", value=None, key=f"{key_prefix}_end_date")

    if enable_country:
        countries = get_available_countries()
        selected_country = st.sidebar.selectbox(
            "Country Filter",
            options=countries,
            index=0,
            key=f"{key_prefix}_country",
        )

    if enable_limit:
        limit = st.sidebar.slider(
            "Top Records Count",
            min_value=5,
            max_value=30,
            value=10,
            step=5,
            key=f"{key_prefix}_limit",
        )

    return start_date, end_date, selected_country, limit
