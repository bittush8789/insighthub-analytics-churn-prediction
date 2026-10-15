"""Pytest test configuration and shared fixtures."""

from datetime import datetime
from decimal import Decimal
from typing import Generator
import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.database.models import Base, Customer, Order, OrderItem, Product


@pytest.fixture
def sample_raw_dataframe() -> pd.DataFrame:
    """Fixture providing raw sales data representing common real-world conditions."""
    return pd.DataFrame([
        # 1. Standard completed transaction
        {
            "Invoice": "536365",
            "StockCode": "85123A",
            "Description": "WHITE HANGING HEART T-LIGHT HOLDER",
            "Quantity": "6",
            "InvoiceDate": "2023-01-10 08:26:00",
            "Price": "2.55",
            "Customer ID": "17850",
            "Country": "United Kingdom",
        },
        # 2. Second item on same invoice
        {
            "Invoice": "536365",
            "StockCode": "71053",
            "Description": "WHITE METAL LANTERN",
            "Quantity": "6",
            "InvoiceDate": "2023-01-10 08:26:00",
            "Price": "3.39",
            "Customer ID": "17850",
            "Country": "United Kingdom",
        },
        # 3. Cancellation / Return (Negative quantity and 'C' invoice)
        {
            "Invoice": "C536379",
            "StockCode": "D",
            "Description": "Discount",
            "Quantity": "-1",
            "InvoiceDate": "2023-01-11 09:41:00",
            "Price": "27.50",
            "Customer ID": "17850",
            "Country": "United Kingdom",
        },
        # 4. Guest checkout (Missing customer ID)
        {
            "Invoice": "536380",
            "StockCode": "22720",
            "Description": "SET OF 3 CAKE TINS PANTRY DESIGN",
            "Quantity": "3",
            "InvoiceDate": "2023-01-12 10:15:00",
            "Price": "4.95",
            "Customer ID": "",
            "Country": "France",
        },
        # 5. Invalid record: Non-positive unit price (should be rejected)
        {
            "Invoice": "536381",
            "StockCode": "84879",
            "Description": "Damaged stock adjustment",
            "Quantity": "10",
            "InvoiceDate": "2023-01-12 11:00:00",
            "Price": "0.00",
            "Customer ID": "13047",
            "Country": "United Kingdom",
        },
        # 6. Invalid record: Zero quantity (should be rejected)
        {
            "Invoice": "536382",
            "StockCode": "22423",
            "Description": "REGENCY CAKESTAND 3 TIER",
            "Quantity": "0",
            "InvoiceDate": "2023-01-12 12:00:00",
            "Price": "12.75",
            "Customer ID": "13047",
            "Country": "United Kingdom",
        },
    ])


@pytest.fixture
def sqlite_test_session() -> Generator[Session, None, None]:
    """In-memory SQLite database session fixture for isolated testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
