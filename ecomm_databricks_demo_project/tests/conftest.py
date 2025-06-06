# File: /Workspace/Users/sdinesh38@gmail.com/portfolio-projects/ecomm_databricks_demo_project/tests/conftest.py

import pytest
from datetime import date
from pyspark.sql import SparkSession,DataFrame
from pyspark.sql.types import StructType, StructField, StringType, LongType, IntegerType, DoubleType, DateType, TimestampType
from pyspark.sql.functions import lit, col, year
import os
from unittest.mock import patch, MagicMock
from transform_functions.ingest_customer_data_functions import customer_schema as raw_customer_file_schema_definition
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


@pytest.fixture(scope="function")
def temp_delta_path(tmp_path):
    """
    Pytest fixture to create a temporary directory for Delta tables.
    `tmp_path` is a built-in pytest fixture for creating temporary directories.
    """
    path = tmp_path / "delta_customers"
    yield str(path)
    # Cleanup: pytest's tmp_path fixture handles cleanup automatically
    # if you return path directly. If you explicitly create a sub-dir like this
    # you might want to ensure it's removed, but tmp_path typically cleans up its root.
    # For safety, if tmp_path doesn't clean subdirs automatically, you can add:
    # if os.path.exists(path):
    #     shutil.rmtree(path)

@pytest.fixture
def mock_dbutils():
    """
    Mocks the dbutils object for file system operations.
    """
    mock = MagicMock()
    # Ensure .fs.mkdirs exists and does nothing
    mock.fs.mkdirs.return_value = None
    return mock

@pytest.fixture
def mock_raw_orders_data():
    """
    Provides mock raw data for orders as a list of tuples (10 records).
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
# --- Customer Schema (Camel Case as used for raw reading) ---
@pytest.fixture(scope="session")
def customer_schema():
    """
    Provides the raw customer DataFrame schema (Camel Case) as used for initial file reading.
    This is directly from transform_functions.ingest_customer_data_functions.customer_schema.
    """
    return raw_customer_file_schema_definition

# --- Mock Raw Customer Data (Camel Case, matches customer_schema) ---
@pytest.fixture
def mock_raw_customers_data():
    """
    Provides mock raw customer data with Camel Case column names,
    conforming to the 'customer_schema' (which is the raw file schema).
    Includes a record with a null customer_id for testing null handling later.
    """
    return [
        ("C001", "Alice", "alice@example.com", "123-456-7890", "123 Main St", "Premium", "USA", "Anytown", "CA", "90210", "West"),
        (None, "Bob", "bob@example.com", "098-765-4321", "456 Oak Ave", "Basic", "Canada", "Otherville", "ON", "M1A1A1", "East"), # Null customer_id
        ("C003", "Charlie", "charlie@example.com", "111-222-3333", "789 Pine Ln", "Gold", "Mexico", "Somewhere", "MX", "01000", "South"),
    ]



# --- Mock Raw Customer DataFrame (Camel Case, derived from mock_raw_customers_data and customer_schema) ---
@pytest.fixture
def mock_raw_customers_df(spark_session, mock_raw_customers_data, customer_schema):
    """
    Creates a mock Spark DataFrame for raw customers with Camel Case columns,
    using the 'customer_schema' (raw file schema).
    """
    return spark_session.createDataFrame(mock_raw_customers_data, schema=customer_schema)


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
        ("P_NO_CATEGORY", "Misc", None, "Misc Item", "Unknown", 5.00),
    ]

@pytest.fixture
def mock_raw_products_df(spark_session, mock_raw_products_data):
    """
    Creates a mock Spark DataFrame for products using the imported products_schema.
    """
    return spark_session.createDataFrame(mock_raw_products_data, schema=products_schema)


@pytest.fixture
def mock_add_ingestion_date_func():
    """
    Provides a MagicMock callable that simulates the add_ingestion_date function
    by adding an 'ingestion_timestamp' column with current timestamp.
    """
    mock_func = MagicMock()
    # The side_effect makes the mock behave like a function that takes a DataFrame
    # and returns it with the 'ingestion_timestamp' column added.
    mock_func.side_effect = lambda df: df.withColumn("ingestion_timestamp", current_timestamp())
    return mock_func
