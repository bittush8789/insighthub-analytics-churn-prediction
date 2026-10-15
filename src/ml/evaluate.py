"""Model evaluation metrics and decision threshold tuning."""

import logging
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

logger = logging.getLogger(__name__)


def evaluate_classifier(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    threshold: float = 0.50,
) -> Dict[str, Any]:
    """Calculate comprehensive classification metrics at a given decision threshold.

    Args:
        y_true: Ground truth binary labels (0 = retained, 1 = churned).
        y_prob: Predicted churn probabilities.
        threshold: Probability cutoff for positive classification.

    Returns:
        Dictionary of performance metrics and trade-off insights.
    """
    y_true = np.asarray(y_true)
    y_prob = np.asarray(y_prob)
    y_pred = (y_prob >= threshold).astype(int)

    # Core Metrics
    precision = float(precision_score(y_true, y_pred, zero_division=0))
    recall = float(recall_score(y_true, y_pred, zero_division=0))
    f1 = float(f1_score(y_true, y_pred, zero_division=0))

    try:
        roc_auc = float(roc_auc_score(y_true, y_prob))
    except ValueError:
        roc_auc = 0.50

    try:
        pr_auc = float(average_precision_score(y_true, y_prob))
    except ValueError:
        pr_auc = float(y_true.mean())

    cm = confusion_matrix(y_true, y_pred)
    tn, fp, fn, tp = [int(v) for v in cm.ravel()] if cm.size == 4 else (0, 0, 0, 0)

    # Business Trade-off Explanation
    trade_off_explanation = (
        f"At threshold {threshold:.2f}: "
        f"Detected {tp} true churners ({recall * 100:.1f}% recall). "
        f"False Positives: {fp} retained customers flagged at risk (wasting retention discounts). "
        f"False Negatives: {fn} unpredicted churners lost without intervention."
    )

    return {
        "threshold": round(threshold, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1_score": round(f1, 4),
        "roc_auc": round(roc_auc, 4),
        "pr_auc": round(pr_auc, 4),
        "confusion_matrix": {
            "true_negatives": tn,
            "false_positives": fp,
            "false_negatives": fn,
            "true_positives": tp,
        },
        "support": {
            "total_samples": len(y_true),
            "actual_churners": int(y_true.sum()),
            "actual_retained": int((y_true == 0).sum()),
            "base_churn_rate": round(float(y_true.mean()), 4),
        },
        "trade_off_analysis": trade_off_explanation,
    }


def tune_decision_threshold(
    y_val_true: np.ndarray,
    y_val_prob: np.ndarray,
    candidate_thresholds: Optional[List[float]] = None,
) -> Tuple[float, Dict[str, Any]]:
    """Select the optimal probability threshold on validation data to maximize F1-score.

    Args:
        y_val_true: Validation ground truth.
        y_val_prob: Validation predicted probabilities.
        candidate_thresholds: List of candidate thresholds to test.

    Returns:
        Tuple of (best_threshold, evaluation_metrics_dict).
    """
    if candidate_thresholds is None:
        candidate_thresholds = [round(x, 2) for x in np.arange(0.15, 0.85, 0.05)]

    best_thresh = 0.50
    best_f1 = -1.0
    best_metrics = {}

    for thresh in candidate_thresholds:
        metrics = evaluate_classifier(y_val_true, y_val_prob, threshold=thresh)
        if metrics["f1_score"] > best_f1:
            best_f1 = metrics["f1_score"]
            best_thresh = thresh
            best_metrics = metrics

    logger.info(
        "Tuned decision threshold to %.2f on validation set (F1: %.4f, Recall: %.4f, Precision: %.4f)",
        best_thresh,
        best_metrics["f1_score"],
        best_metrics["recall"],
        best_metrics["precision"],
    )
    return best_thresh, best_metrics
