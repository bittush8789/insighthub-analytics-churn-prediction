"""Generate and optionally ingest a synthetic transaction fixture for testing and verification.

IMPORTANT NOTICE:
This script generates purely SYNTHETIC data designed strictly for unit/integration testing
and local verification when the official UCI Online Retail II dataset is not yet downloaded.
All product descriptions are explicitly prefixed with '[SYNTHETIC]'.
"""

import argparse
import csv
import logging
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.config.logging_config import setup_logging
from src.data.ingestion import DataIngestionPipeline
from src.database.connection import check_db_connection, init_db

logger = setup_logging()

COUNTRIES = ["United Kingdom", "Germany", "France", "EIRE", "Spain"]
PRODUCTS = [
    ("21212", "[SYNTHETIC] Pack of 72 Retrospot Cake Cases", 1.25),
    ("85123A", "[SYNTHETIC] White Hanging Heart T-Light Holder", 2.95),
    ("84879", "[SYNTHETIC] Assorted Colour Bird Ornament", 1.69),
    ("22423", "[SYNTHETIC] Regency Cakestand 3 Tier", 12.75),
    ("47566", "[SYNTHETIC] Party Bunting", 4.95),
    ("20725", "[SYNTHETIC] Lunch Bag Red Retrospot", 1.65),
    ("22720", "[SYNTHETIC] Set of 3 Cake Tins Pantry Design", 4.95),
    ("POST", "[SYNTHETIC] Postage Fee", 18.00),
]


def generate_synthetic_csv(output_path: Path, num_records: int = 500, seed: int = 42) -> Path:
    """Generate synthetic retail CSV file conforming to UCI dataset schema."""
    random.seed(seed)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    base_date = datetime(2023, 1, 1, 9, 30, 0)
    customer_ids = [f"1{random.randint(1000, 9999)}" for _ in range(35)]

    rows = []
    current_invoice_num = 536365

    for i in range(num_records):
        # 8% chance to advance invoice number
        if random.random() < 0.25:
            current_invoice_num += 1

        sku, desc, price = random.choice(PRODUCTS)
        qty = random.randint(1, 12)

        # 5% cancellations
        is_cancel = random.random() < 0.05
        if is_cancel:
            invoice_str = f"C{current_invoice_num}"
            qty = -random.randint(1, 3)
        else:
            invoice_str = str(current_invoice_num)

        # 10% missing customer ID (guest checkouts)
        if random.random() < 0.10:
            cust_id = ""
        else:
            cust_id = random.choice(customer_ids)

        country = random.choice(COUNTRIES)
        # Advance date chronologically across 18 months
        days_offset = int((i / num_records) * 540)
        row_date = base_date + timedelta(days=days_offset, minutes=random.randint(0, 1440))

        rows.append({
            "Invoice": invoice_str,
            "StockCode": sku,
            "Description": desc,
            "Quantity": qty,
            "InvoiceDate": row_date.strftime("%Y-%m-%d %H:%M:%S"),
            "Price": f"{price:.2f}",
            "Customer ID": cust_id,
            "Country": country,
        })

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["Invoice", "StockCode", "Description", "Quantity", "InvoiceDate", "Price", "Customer ID", "Country"],
        )
        writer.writeheader()
        writer.writerows(rows)

    logger.info("Generated %d synthetic transaction lines at %s", len(rows), output_path)
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic retail transaction fixture.")
    parser.add_argument("--records", type=int, default=500, help="Number of synthetic transaction lines.")
    parser.add_argument("--ingest", action="store_true", help="Automatically ingest generated fixture into PostgreSQL.")
    args = parser.parse_args()

    out_file = ROOT_DIR / "data" / "raw" / "synthetic_demo_transactions.csv"
    generate_synthetic_csv(out_file, num_records=args.records)
    print(f"[OK] Generated synthetic dataset fixture at: {out_file}")

    if args.ingest:
        if not check_db_connection():
            logger.error("Cannot ingest: Database is offline.")
            sys.exit(1)
        init_db()
        pipeline = DataIngestionPipeline()
        summary = pipeline.run(out_file)
        print(f"[OK] Ingested synthetic fixture into database. Accepted: {summary.accepted_rows}, Net Revenue: ${float(summary.net_revenue):,.2f}")


if __name__ == "__main__":
    main()
