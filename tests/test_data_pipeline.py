"""Unit tests for the data ingestion, validation, and cleaning layer."""

from decimal import Decimal
import pandas as pd
import pytest

from src.data.cleaning import clean_and_normalize_data
from src.data.validation import validate_required_columns
from src.database.repository import DatabaseRepository
from src.utils.exceptions import DataValidationError


def test_valid_input_processed_correctly(sample_raw_dataframe):
    """Test that valid rows are accepted, types converted, and dimensions populated."""
    customers, products, orders, items, summary = clean_and_normalize_data(
        sample_raw_dataframe, batch_id="TEST_BATCH_001"
    )

    assert summary.total_input_rows == 6
    # 2 invalid rows (price=0.0 and qty=0) should be rejected
    assert summary.rejected_rows == 2
    assert summary.accepted_rows == 4

    # Dimension entities
    assert len(customers) == 1  # Customer 17850
    assert customers[0]["customer_id"] == "17850"

    # Products should contain 85123A, 71053, D, 22720
    assert len(products) == 4
    # Orders: 536365, C536379, 536380
    assert len(orders) == 3
    assert len(items) == 4


def test_missing_required_columns_raises_error():
    """Test that missing mandatory columns raises DataValidationError."""
    bad_df = pd.DataFrame([{"Quantity": 5, "Price": 10.0}])  # Missing invoice, stock_code, date
    with pytest.raises(DataValidationError) as exc:
        validate_required_columns(bad_df)
    assert "mandatory columns" in str(exc.value)


def test_returns_and_cancellations_reconciliation(sample_raw_dataframe):
    """Verify that cancellations are isolated and net revenue reconciles correctly."""
    _, _, _, _, summary = clean_and_normalize_data(sample_raw_dataframe, batch_id="TEST_BATCH_RECON")

    # Row 1: 6 * 2.55 = 15.30
    # Row 2: 6 * 3.39 = 20.34
    # Row 4: 3 * 4.95 = 14.85
    # Total Gross: 15.30 + 20.34 + 14.85 = 50.49
    # Row 3 (Cancellation): 1 * 27.50 = 27.50 returns
    # Net Revenue: 50.49 - 27.50 = 22.99
    expected_gross = Decimal("50.49")
    expected_returns = Decimal("27.50")
    expected_net = Decimal("22.99")

    assert summary.cancellation_rows == 1
    assert summary.gross_sales == expected_gross
    assert summary.returns_amount == expected_returns
    assert summary.net_revenue == expected_net


def test_duplicate_rows_detected():
    """Verify that duplicate rows within a batch are flagged in audit summary."""
    dup_df = pd.DataFrame([
        {
            "Invoice": "10001",
            "StockCode": "SKU1",
            "Description": "Item 1",
            "Quantity": "2",
            "InvoiceDate": "2023-05-01 10:00:00",
            "Price": "5.00",
            "Customer ID": "CUST1",
            "Country": "UK",
        },
        {
            "Invoice": "10001",
            "StockCode": "SKU1",
            "Description": "Item 1",
            "Quantity": "2",
            "InvoiceDate": "2023-05-01 10:00:00",
            "Price": "5.00",
            "Customer ID": "CUST1",
            "Country": "UK",
        },
    ])
    _, _, _, _, summary = clean_and_normalize_data(dup_df, batch_id="DUP_TEST")
    assert summary.duplicate_rows == 1


def test_idempotent_ingestion(sqlite_test_session, sample_raw_dataframe):
    """Test that repeated persistence does not create duplicate items with same line hash."""
    repo = DatabaseRepository(sqlite_test_session)
    customers, products, orders, items, _ = clean_and_normalize_data(sample_raw_dataframe, "BATCH_IDEMP")

    # First insert
    repo.upsert_products(products)
    repo.upsert_customers(customers)
    repo.insert_orders_and_items(orders, items)

    # Second insert with identical items
    repo.insert_orders_and_items(orders, items)

    from src.database.models import OrderItem
    from sqlalchemy import func, select

    total_items = sqlite_test_session.scalar(select(func.count(OrderItem.item_id)))
    # Total should equal the original item count (4), not doubled
    assert total_items == 4
