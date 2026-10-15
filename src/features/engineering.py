"""Point-in-time RFM and behavioral feature engineering avoiding temporal data leakage."""

import logging
from datetime import date, datetime, timedelta
from typing import List, Optional
import numpy as np
import pandas as pd

from src.utils.exceptions import DataValidationError

logger = logging.getLogger(__name__)


class PointInTimeFeatureExtractor:
    """Extracts historical customer features at a strictly defined snapshot date."""

    def __init__(self, lookback_days: int = 365):
        self.lookback_days = lookback_days

    def extract_features(
        self,
        orders_df: pd.DataFrame,
        snapshot_date: date,
        min_orders: int = 1,
    ) -> pd.DataFrame:
        """Extract customer features strictly on or before snapshot_date.

        Args:
            orders_df: DataFrame of orders with columns:
                ['customer_id', 'order_id', 'order_date', 'net_amount', 'is_cancellation', 'country']
            snapshot_date: Anchor date for point-in-time feature extraction.
            min_orders: Minimum number of completed orders required for inclusion.

        Returns:
            DataFrame of customer features indexed by customer_id.
        """
        if orders_df.empty:
            return pd.DataFrame()

        # Ensure order_date is timezone-naive or datetime for comparison
        df = orders_df.copy()
        if not pd.api.types.is_datetime64_any_dtype(df["order_date"]):
            df["order_date"] = pd.to_datetime(df["order_date"])

        # Eliminate rows with missing customer_id
        df = df[df["customer_id"].notna() & (df["customer_id"] != "")].copy()
        if df.empty:
            return pd.DataFrame()

        # Snapshot timestamp cutoff (end of snapshot day)
        snapshot_ts = pd.Timestamp(snapshot_date) + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
        lookback_cutoff = snapshot_ts - pd.Timedelta(days=self.lookback_days)

        # STRICT POINT-IN-TIME FILTERING: only orders within [lookback_cutoff, snapshot_ts]
        historical_orders = df[
            (df["order_date"] <= snapshot_ts) & (df["order_date"] >= lookback_cutoff)
        ].copy()

        if historical_orders.empty:
            logger.warning("No orders found prior to snapshot date %s within lookback window.", snapshot_date)
            return pd.DataFrame()

        # Sort chronologically
        historical_orders = historical_orders.sort_values(["customer_id", "order_date"])

        feature_rows = []
        for cust_id, group in historical_orders.groupby("customer_id"):
            completed_orders = group[group["is_cancellation"] == False]
            freq = len(completed_orders["order_id"].unique())

            if freq < min_orders:
                continue

            # Recency in days relative to snapshot_date
            last_order_dt = completed_orders["order_date"].max()
            recency_days = max(int((snapshot_ts - last_order_dt).total_seconds() // 86400), 0)

            # Customer Tenure in days
            first_order_dt = completed_orders["order_date"].min()
            tenure_days = max(int((snapshot_ts - first_order_dt).total_seconds() // 86400), 0)

            # Monetary metrics
            monetary_value = float(group["net_amount"].sum())
            aov = monetary_value / freq if freq > 0 else 0.0

            # Purchase Intervals
            sorted_dates = completed_orders["order_date"].drop_duplicates().sort_values()
            if len(sorted_dates) > 1:
                intervals = sorted_dates.diff().dt.total_seconds().dropna() / 86400.0
                interval_avg = float(intervals.mean())
                interval_std = float(intervals.std(ddof=0)) if len(intervals) > 1 else 0.0
            else:
                interval_avg = 0.0
                interval_std = 0.0

            # Return Rate
            total_lines = len(group)
            cancelled_lines = len(group[group["is_cancellation"] == True])
            return_rate = (cancelled_lines / total_lines) if total_lines > 0 else 0.0

            # Primary country
            primary_country = group["country"].mode().iloc[0] if not group["country"].empty else "Unknown"

            feature_rows.append({
                "customer_id": str(cust_id),
                "snapshot_date": snapshot_date,
                "recency_days": recency_days,
                "frequency": freq,
                "monetary_value": round(monetary_value, 2),
                "average_order_value": round(aov, 2),
                "purchase_interval_avg": round(interval_avg, 2),
                "purchase_interval_std": round(interval_std, 2),
                "return_rate": round(return_rate, 4),
                "tenure_days": tenure_days,
                "country": primary_country,
            })

        features_df = pd.DataFrame(feature_rows)
        logger.info(
            "Extracted point-in-time features for %d customers at snapshot %s",
            len(features_df),
            snapshot_date,
        )
        return features_df
