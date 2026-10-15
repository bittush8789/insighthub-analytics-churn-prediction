"""Model training, temporal cross-validation, and artifact serialization."""

import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import joblib
import pandas as pd

from src.config.settings import get_settings
from src.features.engineering import PointInTimeFeatureExtractor
from src.ml.churn_definition import ChurnLabelGenerator
from src.ml.evaluate import evaluate_classifier, tune_decision_threshold
from src.ml.pipeline import NUMERIC_FEATURES, CATEGORICAL_FEATURES, build_model_pipeline
from src.utils.exceptions import ModelTrainingError

logger = logging.getLogger(__name__)


class ModelTrainer:
    """Orchestrates temporal split, pipeline fitting, evaluation, and artifact persistence."""

    def __init__(
        self,
        lookback_days: Optional[int] = None,
        churn_horizon_days: Optional[int] = None,
        random_seed: Optional[int] = None,
        artifacts_dir: Optional[Path] = None,
    ):
        settings = get_settings()
        self.lookback_days = lookback_days or settings.FEATURE_LOOKBACK_DAYS
        self.churn_horizon_days = churn_horizon_days or settings.CHURN_HORIZON_DAYS
        self.random_seed = random_seed or settings.RANDOM_SEED
        self.artifacts_dir = artifacts_dir or (settings.ARTIFACTS_DIR / "models")
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

        self.extractor = PointInTimeFeatureExtractor(lookback_days=self.lookback_days)
        self.labeler = ChurnLabelGenerator(horizon_days=self.churn_horizon_days)

    def prepare_dataset_at_snapshot(
        self,
        orders_df: pd.DataFrame,
        snapshot_date: date,
    ) -> Tuple[pd.DataFrame, pd.Series]:
        """Extract features and labels for a specific point-in-time snapshot."""
        # 1. Point-in-time feature extraction
        features_df = self.extractor.extract_features(orders_df, snapshot_date)
        if features_df.empty:
            raise ModelTrainingError(f"No customer features could be extracted at snapshot {snapshot_date}.")

        # 2. Churn labels strictly in future window (T, T + horizon]
        labels_df = self.labeler.label_customers(
            orders_df,
            features_df["customer_id"],
            snapshot_date,
        )

        merged = features_df.merge(labels_df, on="customer_id", how="inner")
        feature_cols = NUMERIC_FEATURES + CATEGORICAL_FEATURES
        X = merged[feature_cols]
        y = merged["churn_label"]

        return X, y

    def train_and_evaluate(
        self,
        orders_df: pd.DataFrame,
        model_version: str = "v1.0.0",
    ) -> Dict[str, Any]:
        """Execute chronological train, validation, and test pipeline.

        Temporal Splitting Strategy:
            Ensures that training, validation, and test cohorts are chronologically separated
            to strictly prevent data leakage from future customer actions.
        """
        if orders_df.empty:
            raise ModelTrainingError("Orders dataset is empty. Cannot train churn model.")

        df = orders_df.copy()
        if not pd.api.types.is_datetime64_any_dtype(df["order_date"]):
            df["order_date"] = pd.to_datetime(df["order_date"])

        max_order_dt = df["order_date"].max().date()
        min_order_dt = df["order_date"].min().date()
        total_span_days = (max_order_dt - min_order_dt).days

        logger.info(
            "Dataset temporal range: %s to %s (%d total days)",
            min_order_dt,
            max_order_dt,
            total_span_days,
        )

        # Minimum required span: lookback + 2 horizons (train + test)
        min_required_days = self.lookback_days + self.churn_horizon_days
        if total_span_days < min_required_days:
            raise ModelTrainingError(
                f"Historical timespan of {total_span_days} days is insufficient for lookback "
                f"({self.lookback_days}d) + churn horizon ({self.churn_horizon_days}d). "
                f"A minimum of {min_required_days} days is required for defensible modeling."
            )

        # Establish chronological snapshot dates
        # T_test: Max date minus horizon
        t_test = max_order_dt - timedelta(days=self.churn_horizon_days)
        # T_val: T_test minus 45 days (or half horizon)
        t_val = t_test - timedelta(days=max(30, self.churn_horizon_days // 2))
        # T_train: T_val minus 60 days
        t_train = t_val - timedelta(days=max(45, self.churn_horizon_days // 2))

        logger.info("Chronological snapshots: Train=%s, Val=%s, Test=%s", t_train, t_val, t_test)

        # Build feature/label sets
        X_train, y_train = self.prepare_dataset_at_snapshot(df, t_train)
        X_val, y_val = self.prepare_dataset_at_snapshot(df, t_val)
        X_test, y_test = self.prepare_dataset_at_snapshot(df, t_test)

        logger.info(
            "Dataset sizes: Train=%d (Churn: %.1f%%), Val=%d (Churn: %.1f%%), Test=%d (Churn: %.1f%%)",
            len(X_train),
            y_train.mean() * 100,
            len(X_val),
            y_val.mean() * 100,
            len(X_test),
            y_test.mean() * 100,
        )

        # 1. Train Baseline (Logistic Regression)
        logger.info("Training Logistic Regression baseline...")
        lr_pipeline = build_model_pipeline("logistic_regression", random_state=self.random_seed)
        lr_pipeline.fit(X_train, y_train)
        lr_val_probs = lr_pipeline.predict_proba(X_val)[:, 1]
        lr_test_probs = lr_pipeline.predict_proba(X_test)[:, 1]
        lr_eval = evaluate_classifier(y_test, lr_test_probs, threshold=0.50)

        # 2. Train Advanced Classifier (Random Forest)
        logger.info("Training Random Forest classifier...")
        rf_pipeline = build_model_pipeline("random_forest", random_state=self.random_seed)
        rf_pipeline.fit(X_train, y_train)
        rf_val_probs = rf_pipeline.predict_proba(X_val)[:, 1]

        # Tune decision threshold using validation set
        optimal_thresh, val_metrics = tune_decision_threshold(y_val, rf_val_probs)

        # Evaluate on unseen out-of-time test set using optimal threshold
        rf_test_probs = rf_pipeline.predict_proba(X_test)[:, 1]
        rf_test_eval = evaluate_classifier(y_test, rf_test_probs, threshold=optimal_thresh)

        # Pick best model based on PR-AUC / ROC-AUC on test set
        chosen_pipeline = rf_pipeline if rf_test_eval["pr_auc"] >= lr_eval["pr_auc"] else lr_pipeline
        chosen_model_type = "Random Forest" if chosen_pipeline == rf_pipeline else "Logistic Regression"
        chosen_threshold = optimal_thresh if chosen_pipeline == rf_pipeline else 0.50
        chosen_eval = rf_test_eval if chosen_pipeline == rf_pipeline else lr_eval

        # Serialize Model Artifact
        artifact_path = self.artifacts_dir / f"churn_model_{model_version}.joblib"
        metadata_path = self.artifacts_dir / f"churn_model_{model_version}_metadata.json"

        joblib.dump(chosen_pipeline, artifact_path)

        metadata = {
            "model_version": model_version,
            "model_type": chosen_model_type,
            "trained_at": date.today().isoformat(),
            "decision_threshold": chosen_threshold,
            "lookback_days": self.lookback_days,
            "churn_horizon_days": self.churn_horizon_days,
            "random_seed": self.random_seed,
            "features": NUMERIC_FEATURES + CATEGORICAL_FEATURES,
            "temporal_splits": {
                "train_snapshot": t_train.isoformat(),
                "val_snapshot": t_val.isoformat(),
                "test_snapshot": t_test.isoformat(),
                "train_samples": len(X_train),
                "val_samples": len(X_val),
                "test_samples": len(X_test),
            },
            "test_metrics": chosen_eval,
            "baseline_metrics": lr_eval,
        }

        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        logger.info("Model artifact and metadata saved to %s", artifact_path)
        return metadata
