"""CLI Script to generate and persist customer churn predictions.

Usage:
    python scripts/generate_predictions.py --version v1.0.0
    python scripts/generate_predictions.py --version v1.0.0 --snapshot-date 2011-12-01
"""

import argparse
import logging
import sys
from datetime import date, datetime
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
from sqlalchemy import select

from scripts.train_model import load_orders_from_db
from src.config.logging_config import setup_logging
from src.database.connection import check_db_connection, get_db_session
from src.database.repository import DatabaseRepository
from src.features.engineering import PointInTimeFeatureExtractor
from src.ml.predict import ChurnPredictor
from src.utils.helpers import to_decimal

logger = setup_logging()


def parse_args():
    parser = argparse.ArgumentParser(description="Generate customer churn risk predictions.")
    parser.add_argument("--version", type=str, default="v1.0.0", help="Trained model version.")
    parser.add_argument(
        "--snapshot-date",
        type=str,
        default=None,
        help="Anchor date (YYYY-MM-DD) for feature calculation. Defaults to latest transaction date.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if not check_db_connection():
        logger.error("Failed to connect to PostgreSQL. Please check DATABASE_URL in .env.")
        sys.exit(1)

    orders_df = load_orders_from_db()
    if orders_df.empty:
        logger.error("No orders found in database.")
        sys.exit(1)

    # Determine snapshot date
    if args.snapshot_date:
        snapshot_dt = datetime.strptime(args.snapshot_date, "%Y-%m-%d").date()
    else:
        snapshot_dt = pd.to_datetime(orders_df["order_date"]).max().date()

    logger.info("Extracting customer features at snapshot date: %s", snapshot_dt)
    extractor = PointInTimeFeatureExtractor(lookback_days=365)
    features_df = extractor.extract_features(orders_df, snapshot_dt)

    if features_df.empty:
        logger.error("No features could be computed at snapshot date %s.", snapshot_dt)
        sys.exit(1)

    # Save feature vectors to customer_features table
    logger.info("Persisting %d customer feature vectors...", len(features_df))
    feature_records = [
        {
            "customer_id": r["customer_id"],
            "snapshot_date": r["snapshot_date"],
            "recency_days": r["recency_days"],
            "frequency": r["frequency"],
            "monetary_value": to_decimal(r["monetary_value"]),
            "average_order_value": to_decimal(r["average_order_value"]),
            "purchase_interval_avg": to_decimal(r["purchase_interval_avg"]),
            "purchase_interval_std": to_decimal(r["purchase_interval_std"]),
            "return_rate": to_decimal(r["return_rate"]),
        }
        for _, r in features_df.iterrows()
    ]
    with get_db_session() as session:
        repo = DatabaseRepository(session)
        repo.save_customer_features(feature_records)

    # Generate predictions
    logger.info("Generating churn predictions using model version '%s'...", args.version)
    predictor = ChurnPredictor(model_version=args.version)
    predictions_df = predictor.predict(features_df, prediction_date=snapshot_dt)

    # Persist predictions
    persisted_count = predictor.persist_predictions(predictions_df)

    # Print summary
    counts = predictions_df["risk_segment"].value_counts().to_dict()
    print("\n================ PREDICTIONS GENERATED ================")
    print(f"Total Customers Scored:  {persisted_count:,}")
    print(f"Prediction Date:         {snapshot_dt}")
    print(f"Model Version:           {args.version}")
    print("\nRisk Segmentation Breakdown:")
    for seg, count in counts.items():
        pct = (count / persisted_count) * 100
        print(f"  - {seg:12}: {count:,} customers ({pct:.1f}%)")
    print("=======================================================\n")


if __name__ == "__main__":
    main()
