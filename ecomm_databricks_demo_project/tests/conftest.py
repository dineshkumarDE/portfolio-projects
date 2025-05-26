# File: /Workspace/Users/sdinesh38@gmail.com/portfolio-projects/ecomm_databricks_demo_project/tests/conftest.py

import pytest
from datetime import date
from pyspark.sql import SparkSession,DataFrame
from pyspark.sql.types import StructType, StructField, StringType, LongType, IntegerType, DoubleType, DateType, TimestampType
from pyspark.sql.functions import lit, col, year
import os
from unittest.mock import patch, MagicMock
from transform_functions.ingest_customer_data_functions import customer_schema
from transform_functions.ingest_orders_data_functions import orders_schema
from transform_functions.ingest_products_data_functions import products_schema
# --- Fixture for SparkSession ---
@pytest.fixture(scope="session")
def spark_session():
    # In Databricks, the 'spark' object is pre-defined.
    # For local testing outside Databricks, this creates a local SparkSession.
    if 'spark' in globals():
        return globals()['spark']
    else:
        return SparkSession.builder.appName("PytestInDatabricks").getOrCreate()

@pytest.fixture
def mock_raw_customer_data():
    """
    Provides mock raw data for customers as a list of tuples (5 records).
    This data should conform to the customer_schema imported from src.
    """
    return [
        ("C001", "Alice Smith", "alice@example.com", "123-456-7890", "123 Main St", "Consumer", "USA", "New York", "NY", "10001", "East"),
        ("C002", "Bob Johnson", "bob@example.com", "#ERROR!", "456 Oak Ave", "Corporate", "Canada", "Toronto", "ON", "M5V 2C6", "Central"),
        ("C003", None, "charlie@example.com", "987-654-3210", "789 Pine Rd", "Home Office", "UK", "London", "England", "SW1A 0AA", "Europe"),
        ("C004", "Diana Prince", "diana@example.com", None, "101 Lasso Ln", "Consumer", "USA", "Los Angeles", "CA", "90210", "West"),
        ("C005", "Eve Adams", "eve@example.com", "555-123-4567", "555 Elm St", "Corporate", "Australia", "Sydney", "NSW", "2000", "Oceania"),
        ("C_MISSING_NAME", None, "missing@example.com", "111-222-3333", "999 Error St", "Consumer", "Germany", "Berlin", "BE", "10115", "Europe"),
    ]

@pytest.fixture
def mock_raw_customer_df(spark_session, mock_raw_customer_data):
    """
    Creates a mock Spark DataFrame for customers using the imported customer_schema.
    """
    return spark_session.createDataFrame(mock_raw_customer_data, schema=customer_schema)


@pytest.fixture
def mock_raw_orders_data():
    """
    Provides mock raw data for orders as a list of tuples (5 records).
    This data should conform to the orders_schema imported from src.
    """
    return [
        (1, "O1", date(2025, 1, 1), date(2025, 1, 5), "Standard", "C1", "P1", 10, 100.0, 0.1, 10.0),
        (2, "O2", date(2025, 1, 2), date(2025, 1, 6), "Fast", "C2", "P2", 5, 50.0, 0.05, 5.0),
        (3, "O3", date(2025, 1, 3), date(2025, 1, 7), "Same Day", "C3", "P3", 2, 20.0, 0.0, 2.0),
        (4, "O4", date(2025, 1, 4), date(2025, 1, 8), "Standard", "C4", "P4", 7, 75.0, 0.15, 11.25),
        (5, "O5", date(2025, 1, 5), date(2025, 1, 9), "Express", "C5", "P5", 1, 120.0, 0.2, 24.0),
        (6, "O6", date(2025, 1, 10), date(2025, 1, 15), "Standard", "C001", "P001", 3, 30.0, 0.1, 3.0),
        # ADDED: Record for different year for aggregation test
        (7, "O7", date(2024, 12, 1), date(2024, 12, 5), "Standard", "C001", "P001", 2, 20.0, 0.1, 2.0),
        # ADDED: Record with a non-existent customer_id for join test
        (8, "O8", date(2025, 2, 1), date(2025, 2, 5), "Fast", "C_NONEXISTENT", "P001", 5, 50.0, 0.1, 5.0),
        # ADDED: Record with a non-existent product_id for join test
        (9, "O9", date(2025, 3, 1), date(2025, 3, 5), "Standard", "C001", "P_NONEXISTENT", 8, 80.0, 0.1, 8.0),
        # ADDED: Record with a null profit for aggregation test (sum should ignore it)
        (10, "O10", date(2025, 4, 1), date(2025, 4, 5), "Standard", "C002", "P002", 1, 10.0, 0.05, None),
    ]

@pytest.fixture
def mock_raw_orders_df(spark_session, mock_raw_orders_data):
    """
    Creates a mock Spark DataFrame for orders using the imported orders_schema.
    """
    return spark_session.createDataFrame(mock_raw_orders_data, schema=orders_schema)


@pytest.fixture
def mock_raw_products_data():
    """
    Provides mock raw data for products as a list of tuples (5 records).
    This data should conform to the products_schema imported from src.
    """
    return [
        ("P001", "Electronics", "Phones", "Smartphone X", "California", 999.99),
        ("P002", "Office Supplies", "Paper", "Printer Paper", "New York", 25.50),
        ("P003", "Furniture", "Chairs", "Executive Chair", "Texas", 350.00),
        ("P004", "Technology", "Laptops", "Gaming Laptop", "Florida", 1500.00),
        ("P005", "Books", "Fiction", "Sci-Fi Novel", "Washington", 15.00),
           # ADDED: Record with a null sub_category for aggregation test (should group correctly)
        ("P_NO_CATEGORY", "Misc", None, "Misc Item", "Unknown", 5.00),
    ]

@pytest.fixture
def mock_raw_products_df(spark_session, mock_raw_products_data):
    """
    Creates a mock Spark DataFrame for products using the imported products_schema.
    """
    return spark_session.createDataFrame(mock_raw_products_data, schema=products_schema)

@pytest.fixture
def mock_add_ingestion_date_func(): # Renamed to clearly indicate it's a function mock
    """
    Provides a MagicMock callable that simulates the add_ingestion_date function.
    """
    mock_func = MagicMock()
    mock_func.side_effect = lambda df: df.withColumn("ingestion_date", lit("2025-05-23T10:00:00Z").cast("timestamp"))
    return mock_func

