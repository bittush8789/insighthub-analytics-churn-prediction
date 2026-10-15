"""Churn inference engine, risk segmentation, and prediction persistence."""

import json
import logging
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional
import joblib
import numpy as np
import pandas as pd

from src.config.settings import get_settings
from src.database.connection import get_db_session
from src.database.repository import DatabaseRepository
from src.ml.pipeline import NUMERIC_FEATURES, CATEGORICAL_FEATURES
from src.utils.exceptions import PredictionError
from src.utils.helpers import to_decimal

logger = logging.getLogger(__name__)


def assign_risk_segment(prob: float) -> str:
    """Categorize probability into business risk segments.

    Note:
        These risk segments represent probabilistic tendencies based on historical behavior,
        NOT guaranteed outcomes or certainties.
    """
    if prob >= 0.65:
        return "High Risk"
    elif prob >= 0.35:
        return "Medium Risk"
    else:
        return "Low Risk"


class ChurnPredictor:
    """Loads trained model artifacts and generates risk scores."""

    def __init__(self, model_version: str = "v1.0.0", artifacts_dir: Optional[Path] = None):
        settings = get_settings()
        self.model_version = model_version
        self.artifacts_dir = artifacts_dir or (settings.ARTIFACTS_DIR / "models")
        self.pipeline = None
        self.metadata: Dict[str, Any] = {}
        self._load_artifact()

    def _load_artifact(self) -> None:
        """Load serialized pipeline and configuration metadata."""
        artifact_path = self.artifacts_dir / f"churn_model_{self.model_version}.joblib"
        metadata_path = self.artifacts_dir / f"churn_model_{self.model_version}_metadata.json"

        if not artifact_path.exists() or not metadata_path.exists():
            raise PredictionError(
                f"Model artifact or metadata for version '{self.model_version}' not found at {artifact_path}. "
                f"Please train the model first using scripts/train_model.py."
            )

        try:
            self.pipeline = joblib.load(artifact_path)
            with open(metadata_path, "r", encoding="utf-8") as f:
                self.metadata = json.load(f)
            logger.info("Loaded churn prediction pipeline '%s' (%s)", self.model_version, self.metadata.get("model_type"))
        except Exception as exc:
            logger.error("Failed to load model artifact: %s", exc)
            raise PredictionError(f"Error loading model artifact: {exc}") from exc

    def predict(
        self,
        features_df: pd.DataFrame,
        prediction_date: Optional[date] = None,
    ) -> pd.DataFrame:
        """Generate churn risk probabilities and segments for a feature DataFrame.

        Args:
            features_df: DataFrame containing required RFM and behavioral feature columns.
            prediction_date: Effective date of prediction (defaults to today).

        Returns:
            DataFrame containing customer_id, prediction_date, churn_probability,
            risk_segment, model_version, and threshold.
        """
        if self.pipeline is None:
            raise PredictionError("Model pipeline is not loaded.")

        if features_df.empty:
            return pd.DataFrame()

        feature_cols = NUMERIC_FEATURES + CATEGORICAL_FEATURES
        missing_cols = set(feature_cols) - set(features_df.columns)
        if missing_cols:
            raise PredictionError(f"Input features missing required columns: {sorted(list(missing_cols))}")

        pred_date = prediction_date or date.today()
        X = features_df[feature_cols]

        try:
            probs = self.pipeline.predict_proba(X)[:, 1]
        except Exception as exc:
            logger.error("Inference execution failed: %s", exc)
            raise PredictionError(f"Inference error: {exc}") from exc

        model_type = self.metadata.get("model_type", "Random Forest")
        threshold = self.metadata.get("decision_threshold", 0.50)

        results = []
        for i, row in features_df.iterrows():
            prob = float(probs[i]) if i < len(probs) else 0.50
            results.append({
                "customer_id": str(row["customer_id"]),
                "prediction_date": pred_date,
                "churn_probability": round(prob, 4),
                "risk_segment": assign_risk_segment(prob),
                "model_version": self.model_version,
                "model_type": model_type,
                "threshold_applied": threshold,
            })

        return pd.DataFrame(results)

    def persist_predictions(self, predictions_df: pd.DataFrame) -> int:
        """Save predictions to PostgreSQL database."""
        if predictions_df.empty:
            return 0

        records = [
            {
                "customer_id": r["customer_id"],
                "prediction_date": r["prediction_date"],
                "churn_probability": to_decimal(r["churn_probability"]),
                "risk_segment": r["risk_segment"],
                "model_version": r["model_version"],
                "model_type": r["model_type"],
                "threshold_applied": to_decimal(r["threshold_applied"]),
            }
            for _, r in predictions_df.iterrows()
        ]

        with get_db_session() as session:
            repo = DatabaseRepository(session)
            repo.save_churn_predictions(records)

        logger.info("Persisted %d churn predictions for version %s", len(records), self.model_version)
        return len(records)
