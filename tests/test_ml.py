"""Unit tests for machine learning, point-in-time features, and evaluation metrics."""

from datetime import date, datetime
import numpy as np
import pandas as pd
import pytest

from src.features.engineering import PointInTimeFeatureExtractor
from src.ml.churn_definition import ChurnLabelGenerator
from src.ml.evaluate import evaluate_classifier, tune_decision_threshold
from src.ml.pipeline import build_model_pipeline
from src.ml.predict import assign_risk_segment
from src.utils.exceptions import ModelTrainingError


@pytest.fixture
def chronological_orders_df() -> pd.DataFrame:
    """Fixture providing chronologically sequenced customer orders across two years."""
    return pd.DataFrame([
        # Customer 1: Regular continuous buyer
        {"customer_id": "1", "order_id": "O1", "order_date": "2023-01-15", "net_amount": 50.0, "is_cancellation": False, "country": "UK"},
        {"customer_id": "1", "order_id": "O2", "order_date": "2023-03-20", "net_amount": 60.0, "is_cancellation": False, "country": "UK"},
        {"customer_id": "1", "order_id": "O3", "order_date": "2023-07-10", "net_amount": 75.0, "is_cancellation": False, "country": "UK"},
        # Customer 2: Active in early 2023, churns afterwards (no purchases after March 2023)
        {"customer_id": "2", "order_id": "O4", "order_date": "2023-02-10", "net_amount": 120.0, "is_cancellation": False, "country": "France"},
        {"customer_id": "2", "order_id": "O5", "order_date": "2023-03-05", "net_amount": 80.0, "is_cancellation": False, "country": "France"},
        # Customer 3: Future buyer (first purchase in August 2023)
        {"customer_id": "3", "order_id": "O6", "order_date": "2023-08-15", "net_amount": 200.0, "is_cancellation": False, "country": "Germany"},
    ])


def test_point_in_time_features_no_future_leakage(chronological_orders_df):
    """Verify that features computed at snapshot T do not leak any orders after T."""
    extractor = PointInTimeFeatureExtractor(lookback_days=365)
    snapshot = date(2023, 6, 1)

    features = extractor.extract_features(chronological_orders_df, snapshot_date=snapshot)

    # Customer 3 first purchased in August 2023 (after June 1), so they MUST NOT appear in snapshot features!
    cust_ids = set(features["customer_id"].tolist())
    assert "3" not in cust_ids
    assert "1" in cust_ids
    assert "2" in cust_ids

    # For Customer 1, only O1 and O2 were placed before June 1. O3 (July 10) must NOT be included in monetary value.
    c1_row = features[features["customer_id"] == "1"].iloc[0]
    assert c1_row["frequency"] == 2
    assert c1_row["monetary_value"] == 110.0  # 50.0 + 60.0


def test_incomplete_outcome_window_raises_error(chronological_orders_df):
    """Verify that an outcome window exceeding the dataset max date raises ModelTrainingError."""
    labeler = ChurnLabelGenerator(horizon_days=90)
    # Dataset max date is 2023-08-15. A snapshot at 2023-07-01 requires data through 2023-09-29, which is incomplete.
    bad_snapshot = date(2023, 7, 1)

    with pytest.raises(ModelTrainingError) as exc:
        labeler.label_customers(chronological_orders_df, pd.Series(["1", "2"]), snapshot_date=bad_snapshot)
    assert "Insufficient historical coverage" in str(exc.value)


def test_churn_label_assignment(chronological_orders_df):
    """Verify that future purchasers receive label 0 (retained) and non-purchasers receive label 1 (churned)."""
    labeler = ChurnLabelGenerator(horizon_days=90)
    # Snapshot at 2023-05-01. Required outcome window: (2023-05-01, 2023-07-30]
    # Customer 1 purchased O3 on 2023-07-10 -> Retained (0)
    # Customer 2 made no purchases -> Churned (1)
    snapshot = date(2023, 5, 1)
    eligible_custs = pd.Series(["1", "2"])

    labels = labeler.label_customers(chronological_orders_df, eligible_custs, snapshot_date=snapshot)

    c1_label = labels[labels["customer_id"] == "1"]["churn_label"].iloc[0]
    c2_label = labels[labels["customer_id"] == "2"]["churn_label"].iloc[0]

    assert c1_label == 0
    assert c2_label == 1


def test_pipeline_build_and_fit():
    """Verify that the scikit-learn pipeline fits and outputs valid probability range [0, 1]."""
    X_synthetic = pd.DataFrame({
        "recency_days": [10, 45, 120, 200, 15],
        "frequency": [5, 2, 1, 1, 4],
        "monetary_value": [250.0, 95.0, 30.0, 15.0, 180.0],
        "average_order_value": [50.0, 47.5, 30.0, 15.0, 45.0],
        "purchase_interval_avg": [15.0, 30.0, 0.0, 0.0, 12.0],
        "purchase_interval_std": [2.0, 4.0, 0.0, 0.0, 1.5],
        "return_rate": [0.0, 0.1, 0.0, 0.0, 0.05],
        "tenure_days": [120, 90, 30, 20, 150],
        "country": ["UK", "UK", "France", "Germany", "UK"],
    })
    y_synthetic = np.array([0, 0, 1, 1, 0])

    pipeline = build_model_pipeline("random_forest", random_state=42)
    pipeline.fit(X_synthetic, y_synthetic)

    probs = pipeline.predict_proba(X_synthetic)[:, 1]
    assert len(probs) == 5
    assert np.all((probs >= 0.0) & (probs <= 1.0))


def test_classification_metrics_and_tuning():
    """Verify calculation of precision, recall, F1, ROC-AUC, and threshold tuning."""
    y_true = np.array([0, 0, 0, 1, 1, 1])
    y_prob = np.array([0.1, 0.2, 0.4, 0.6, 0.8, 0.9])

    metrics = evaluate_classifier(y_true, y_prob, threshold=0.50)
    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 1.0
    assert metrics["f1_score"] == 1.0
    assert metrics["roc_auc"] == 1.0

    best_thresh, best_metrics = tune_decision_threshold(y_true, y_prob)
    assert 0.0 <= best_thresh <= 1.0
    assert best_metrics["f1_score"] == 1.0


def test_risk_segment_assignment():
    """Verify probabilistic mapping to risk segments."""
    assert assign_risk_segment(0.85) == "High Risk"
    assert assign_risk_segment(0.50) == "Medium Risk"
    assert assign_risk_segment(0.15) == "Low Risk"
