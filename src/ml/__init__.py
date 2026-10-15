"""Machine learning package."""

from src.ml.churn_definition import ChurnLabelGenerator
from src.ml.evaluate import evaluate_classifier, tune_decision_threshold
from src.ml.pipeline import CATEGORICAL_FEATURES, NUMERIC_FEATURES, build_model_pipeline
from src.ml.predict import ChurnPredictor, assign_risk_segment
from src.ml.train import ModelTrainer

__all__ = [
    "NUMERIC_FEATURES",
    "CATEGORICAL_FEATURES",
    "build_model_pipeline",
    "ChurnLabelGenerator",
    "evaluate_classifier",
    "tune_decision_threshold",
    "ModelTrainer",
    "ChurnPredictor",
    "assign_risk_segment",
]
