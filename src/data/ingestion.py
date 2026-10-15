"""Data Ingestion Pipeline for processing CSV and Excel files into PostgreSQL."""

import io
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO, Optional, Union
import pandas as pd

from src.config.settings import get_settings
from src.data.cleaning import clean_and_normalize_data
from src.data.schemas import IngestionAuditSummary
from src.database.connection import get_db_session
from src.database.repository import DatabaseRepository
from src.utils.exceptions import DataValidationError, IngestionError

logger = logging.getLogger(__name__)


class DataIngestionPipeline:
    """Robust, idempotent pipeline for ingesting retail transaction datasets."""

    def __init__(self, batch_size: Optional[int] = None):
        self.settings = get_settings()
        self.batch_size = batch_size or self.settings.BATCH_SIZE

    def load_raw_data(self, source: Union[str, Path, BinaryIO, io.BytesIO]) -> pd.DataFrame:
        """Load data from CSV or Excel file or file-like stream."""
        try:
            if isinstance(source, (str, Path)):
                filepath = Path(source)
                if not filepath.exists():
                    raise IngestionError(f"File not found: {filepath}")

                suffix = filepath.suffix.lower()
                if suffix == ".csv":
                    logger.info("Reading CSV dataset from %s", filepath)
                    return pd.read_csv(filepath, encoding="utf-8", dtype=str)
                elif suffix in (".xlsx", ".xls"):
                    logger.info("Reading Excel dataset from %s", filepath)
                    return pd.read_excel(filepath, dtype=str)
                else:
                    raise IngestionError(f"Unsupported file format: {suffix}. Expected .csv, .xlsx, or .xls")

            # Stream or UploadedFile
            logger.info("Reading dataset from file-like stream")
            try:
                # Try CSV first
                source.seek(0)
                return pd.read_csv(source, dtype=str)
            except Exception:
                source.seek(0)
                return pd.read_excel(source, dtype=str)

        except Exception as exc:
            logger.error("Failed to load raw data: %s", exc)
            raise IngestionError(f"Error loading source data: {exc}") from exc

    def run(
        self,
        source: Union[str, Path, BinaryIO, io.BytesIO],
        batch_id: Optional[str] = None,
    ) -> IngestionAuditSummary:
        """Execute complete ingestion workflow with database transactional safety."""
        batch_id = batch_id or f"BATCH_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        logger.info("Starting ingestion batch %s", batch_id)

        # 1. Load Data
        df = self.load_raw_data(source)
        if df.empty:
            raise DataValidationError("Source dataset is empty.")

        # 2. Clean and Normalize
        logger.info("Validating and normalizing %d input rows for batch %s", len(df), batch_id)
        customers, products, orders, items, summary = clean_and_normalize_data(df, batch_id)

        # 3. Database Persistence inside transaction
        try:
            with get_db_session() as session:
                repo = DatabaseRepository(session)

                # Initialize run audit record
                repo.create_pipeline_run(batch_id=batch_id, total_rows=summary.total_input_rows)

                # Upsert dimensions
                logger.info("Upserting %d unique products", len(products))
                repo.upsert_products(products)

                logger.info("Upserting %d unique customers", len(customers))
                repo.upsert_customers(customers)

                # Insert orders & items in chunked batches
                logger.info("Persisting %d orders and %d items", len(orders), len(items))
                for i in range(0, len(items), self.batch_size):
                    item_chunk = items[i : i + self.batch_size]
                    # Filter matching order headers for this chunk
                    order_ids_in_chunk = {it["order_id"] for it in item_chunk}
                    order_chunk = [o for o in orders if o["order_id"] in order_ids_in_chunk]

                    repo.insert_orders_and_items(order_chunk, item_chunk)

                # Update pipeline audit record
                repo.update_pipeline_run(
                    batch_id=batch_id,
                    status="COMPLETED",
                    accepted_rows=summary.accepted_rows,
                    rejected_rows=summary.rejected_rows,
                    duplicate_rows=summary.duplicate_rows,
                    missing_customer_rows=summary.missing_customer_rows,
                    cancellation_rows=summary.cancellation_rows,
                    error_summary="; ".join(summary.errors[:10]) if summary.errors else None,
                )

            logger.info(
                "Ingestion batch %s completed successfully. Accepted: %d, Rejected: %d, Net Revenue: %.2f",
                batch_id,
                summary.accepted_rows,
                summary.rejected_rows,
                float(summary.net_revenue),
            )
            return summary

        except Exception as exc:
            logger.error("Ingestion batch %s failed with database error: %s", batch_id, exc, exc_info=True)
            # Try recording failed status in separate safe session
            try:
                with get_db_session() as err_session:
                    err_repo = DatabaseRepository(err_session)
                    err_repo.update_pipeline_run(
                        batch_id=batch_id,
                        status="FAILED",
                        accepted_rows=0,
                        rejected_rows=summary.rejected_rows,
                        duplicate_rows=summary.duplicate_rows,
                        missing_customer_rows=summary.missing_customer_rows,
                        cancellation_rows=summary.cancellation_rows,
                        error_summary=str(exc)[:500],
                    )
            except Exception:
                pass
            raise IngestionError(f"Ingestion batch {batch_id} failed: {exc}") from exc
