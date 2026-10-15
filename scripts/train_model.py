"""CLI Script to train and evaluate supervised customer churn models.

Usage:
    python scripts/train_model.py --version v1.0.0 --horizon-days 90 --lookback-days 365
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
from sqlalchemy import select

from src.config.logging_config import setup_logging
from src.database.connection import check_db_connection, get_read_only_session
from src.database.models import Order
from src.ml.train import ModelTrainer

logger = setup_logging()


def parse_args():
    parser = argparse.ArgumentParser(description="Train customer churn prediction models.")
    parser.add_argument("--version", type=str, default="v1.0.0", help="Model version identifier.")
    parser.add_argument("--lookback-days", type=int, default=365, help="Feature extraction lookback window.")
    parser.add_argument("--horizon-days", type=int, default=90, help="Future churn observation horizon.")
    parser.add_argument("--random-seed", type=int, default=42, help="Seed for reproducibility.")
    return parser.parse_args()


def load_orders_from_db() -> pd.DataFrame:
    """Fetch order records from PostgreSQL database."""
    logger.info("Loading order history from PostgreSQL...")
    with get_read_only_session() as session:
        query = select(
            Order.customer_id,
            Order.order_id,
            Order.order_date,
            Order.net_amount,
            Order.is_cancellation,
            Order.country,
        ).where(Order.customer_id.isnot(None))

        results = session.execute(query).fetchall()
        if not results:
            return pd.DataFrame()

        return pd.DataFrame([
            {
                "customer_id": r.customer_id,
                "order_id": r.order_id,
                "order_date": r.order_date,
                "net_amount": float(r.net_amount),
                "is_cancellation": r.is_cancellation,
                "country": r.country,
            }
            for r in results
        ])


def main():
    args = parse_args()

    if not check_db_connection():
        logger.error("Failed to connect to PostgreSQL. Please check DATABASE_URL in .env.")
        sys.exit(1)

    orders_df = load_orders_from_db()
    if orders_df.empty:
        logger.error("No customer orders found in database. Please run scripts/ingest_data.py first.")
        sys.exit(1)

    logger.info("Fetched %d completed order transactions for modeling.", len(orders_df))

    trainer = ModelTrainer(
        lookback_days=args.lookback_days,
        churn_horizon_days=args.horizon_days,
        random_seed=args.random_seed,
    )

    try:
        metadata = trainer.train_and_evaluate(orders_df, model_version=args.version)
        print("\n=================== MODEL TRAINING COMPLETE ===================")
        print(f"Model Version:       {metadata['model_version']}")
        print(f"Model Architecture:  {metadata['model_type']}")
        print(f"Tuned Threshold:     {metadata['decision_threshold']:.2f}")
        print("\n--- Out-of-Time Test Set Performance ---")
        test_m = metadata["test_metrics"]
        print(f"ROC-AUC Score:       {test_m['roc_auc']:.4f}")
        print(f"PR-AUC Score:        {test_m['pr_auc']:.4f} (Baseline: {metadata['baseline_metrics']['pr_auc']:.4f})")
        print(f"F1-Score:            {test_m['f1_score']:.4f}")
        print(f"Recall:              {test_m['recall']:.4f}")
        print(f"Precision:           {test_m['precision']:.4f}")
        print(f"Confusion Matrix:    {test_m['confusion_matrix']}")
        print(f"\nTrade-off Analysis:  {test_m['trade_off_analysis']}")
        print("===============================================================\n")
    except Exception as exc:
        logger.error("Model training failed: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
