"""CLI Script to ingest raw transaction dataset into PostgreSQL.

Usage:
    python scripts/ingest_data.py --file data/raw/online_retail_II.csv
    python scripts/ingest_data.py --file data/raw/online_retail_II.xlsx --batch-size 2000
"""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.config.logging_config import setup_logging
from src.data.ingestion import DataIngestionPipeline
from src.database.connection import check_db_connection, init_db

logger = setup_logging()


def parse_args():
    parser = argparse.ArgumentParser(description="Ingest UCI Online Retail II dataset into PostgreSQL.")
    parser.add_argument(
        "--file",
        "-f",
        type=str,
        required=True,
        help="Path to CSV or Excel file containing transaction records.",
    )
    parser.add_argument(
        "--batch-size",
        "-b",
        type=int,
        default=5000,
        help="Database insertion batch size (default: 5000).",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    filepath = Path(args.file)

    if not filepath.exists():
        logger.error("Dataset file not found at: %s", filepath)
        sys.exit(1)

    logger.info("Checking PostgreSQL database connection...")
    if not check_db_connection():
        logger.error("Failed to connect to PostgreSQL. Please check DATABASE_URL in .env.")
        sys.exit(1)

    # Initialize tables if not already present
    init_db()

    pipeline = DataIngestionPipeline(batch_size=args.batch_size)
    try:
        summary = pipeline.run(filepath)
        logger.info("=== INGESTION SUMMARY ===")
        logger.info("Batch ID: %s", summary.batch_id)
        logger.info("Total Rows: %d", summary.total_input_rows)
        logger.info("Accepted Rows: %d", summary.accepted_rows)
        logger.info("Rejected Rows: %d", summary.rejected_rows)
        logger.info("Duplicate Rows: %d", summary.duplicate_rows)
        logger.info("Missing Customer ID: %d", summary.missing_customer_rows)
        logger.info("Cancellations/Returns: %d", summary.cancellation_rows)
        logger.info("Gross Sales: $%.2f", float(summary.gross_sales))
        logger.info("Returns: $%.2f", float(summary.returns_amount))
        logger.info("Net Revenue: $%.2f", float(summary.net_revenue))
        if summary.rejection_reasons:
            logger.info("Rejections breakdown: %s", summary.rejection_reasons)
        print("\n[OK] Ingestion completed successfully.")
    except Exception as exc:
        logger.error("Ingestion failed: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
