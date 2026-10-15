"""Configurable Churn Definition and Outcome Labeling without Temporal Leakage."""

import logging
from datetime import date, timedelta
from typing import Optional, Tuple
import pandas as pd

from src.utils.exceptions import ModelTrainingError

logger = logging.getLogger(__name__)


class ChurnLabelGenerator:
    """Computes ground truth churn labels based on future purchase behavior.

    Definition:
        A customer active on or before snapshot_date T is defined as CHURNED (label = 1)
        if they place NO qualifying completed orders in the future outcome window (T, T + horizon_days].
        They are defined as RETAINED (label = 0) if they place >= 1 qualifying completed order.
    """

    def __init__(self, horizon_days: int = 90):
        self.horizon_days = horizon_days

    def label_customers(
        self,
        orders_df: pd.DataFrame,
        customer_ids: pd.Series,
        snapshot_date: date,
    ) -> pd.DataFrame:
        """Assign churn outcome labels to eligible customers.

        Args:
            orders_df: Order records with ['customer_id', 'order_id', 'order_date', 'is_cancellation']
            customer_ids: Series of customer IDs eligible at snapshot_date.
            snapshot_date: Anchor point in time T.

        Returns:
            DataFrame with ['customer_id', 'churn_label', 'future_orders_count']

        Raises:
            ModelTrainingError: If dataset does not have sufficient future history for outcome window.
        """
        if orders_df.empty:
            raise ModelTrainingError("Orders dataset is empty; cannot compute churn labels.")

        df = orders_df.copy()
        if not pd.api.types.is_datetime64_any_dtype(df["order_date"]):
            df["order_date"] = pd.to_datetime(df["order_date"])

        # Validate temporal coverage
        dataset_max_date = df["order_date"].max().date()
        required_outcome_end = snapshot_date + timedelta(days=self.horizon_days)

        if dataset_max_date < required_outcome_end:
            raise ModelTrainingError(
                f"Insufficient historical coverage: Dataset max date {dataset_max_date} is earlier than "
                f"required outcome window end {required_outcome_end} (Snapshot: {snapshot_date} + {self.horizon_days}d). "
                f"Cannot generate defensible churn labels."
            )

        # Outcome window boundaries: (T, T + horizon_days]
        outcome_start = pd.Timestamp(snapshot_date) + pd.Timedelta(days=1)
        outcome_end = pd.Timestamp(required_outcome_end) + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)

        # Future completed orders strictly in (T, T + horizon_days]
        future_orders = df[
            (df["order_date"] >= outcome_start)
            & (df["order_date"] <= outcome_end)
            & (df["is_cancellation"] == False)
            & (df["customer_id"].notna())
        ]

        # Count future orders per customer
        future_counts = (
            future_orders.groupby("customer_id")["order_id"]
            .nunique()
            .reset_index(name="future_orders_count")
        )
        future_counts["customer_id"] = future_counts["customer_id"].astype(str)

        # Merge with eligible customers
        eligible_df = pd.DataFrame({"customer_id": customer_ids.astype(str).unique()})
        labeled = eligible_df.merge(future_counts, on="customer_id", how="left")
        labeled["future_orders_count"] = labeled["future_orders_count"].fillna(0).astype(int)

        # Churn: 1 if no future purchases, 0 if >= 1 future purchases
        labeled["churn_label"] = (labeled["future_orders_count"] == 0).astype(int)

        churn_rate = labeled["churn_label"].mean()
        logger.info(
            "Labeled %d customers at snapshot %s (Horizon: %dd). Churn count: %d (%.2f%%)",
            len(labeled),
            snapshot_date,
            self.horizon_days,
            labeled["churn_label"].sum(),
            churn_rate * 100,
        )

        return labeled[["customer_id", "churn_label", "future_orders_count"]]
