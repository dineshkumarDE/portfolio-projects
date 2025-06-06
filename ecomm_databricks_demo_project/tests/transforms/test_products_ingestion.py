import pytest
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import col, lit, current_timestamp, to_date, md5, concat_ws, date_sub
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, DateType, ArrayType, BooleanType, TimestampType
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch, ANY
import os

# Assuming your ingestion code is in a module named 'transform_functions.ingest_products_data_functions'
from transform_functions.ingest_products_data_functions import (
    standardize_products_columns,
    handle_product_id_nulls,
    clean_and_transform_products_data,
    perform_product_data_quality_checks,
    load_raw_products_csv,
    products_schema # Importing for schema definition if needed in tests
)

def test_standardize_products_columns(
    spark_session: SparkSession,
    mock_raw_products_df: DataFrame # This DF now represents the raw, Camel Case input
):
    """
    Tests standardize_products_columns function to ensure:
    1. Columns are renamed from Camel Case to snake_case.
    2. 'file_date' column is correctly added and is of DateType.
    """
    print("\n--- Testing standardize_products_columns ---")

    file_date_str = "2025-05-23"
    expected_file_date = date.fromisoformat(file_date_str)
    print(f"Expected file_date: {expected_file_date}")

    # Call the actual function with the raw (Camel Case) DataFrame
    df_standardized = standardize_products_columns(mock_raw_products_df, file_date_str)

    # Hardcoded list of expected standardized column names
    expected_standardized_columns = [
        "product_id",
        "category",
        "sub_category",
        "product_name",
        "state",
        "price_per_product",
        "file_date"
    ]

    # Assertions
    # 1. Check if all expected snake_case columns are present and no unexpected columns
    assert sorted(df_standardized.columns) == sorted(expected_standardized_columns), \
        f"Standardized columns do not match expected list. Expected: {expected_standardized_columns}, Got: {df_standardized.columns}"

    # 2. Check count of rows (should remain the same)
    assert df_standardized.count() == 6, "Row count changed after standardization."

    # 3. Check data type of 'file_date' and its value
    assert "file_date" in df_standardized.columns
    assert df_standardized.schema["file_date"].dataType == DateType(), \
        "file_date column should be of DateType."
    
    # Verify a specific row's data and the file_date
    first_row = df_standardized.filter(col("product_id") == "P001").collect()[0]
    assert first_row.product_name == "Smartphone X"
    assert first_row.price_per_product == 999.99
    assert first_row.file_date == expected_file_date, \
        f"file_date value is incorrect. Expected {expected_file_date}, got {first_row.file_date}"

    print("standardize_products_columns PASSED.")


def test_handle_product_id_nulls(
    spark_session: SparkSession,
    mock_dbutils: MagicMock,
    tmp_path
):
    """
    Tests handle_product_id_nulls function to ensure:
    1. Records with null 'product_id' are correctly excluded from the returned DataFrame.
    2. Mocking `dbutils` and `DataFrame.write` to prevent actual file system operations.
    """
    print("\n--- Testing handle_product_id_nulls ---")

    file_date_str = "2025-05-23"
    
    # Create a DataFrame with a null product_id for testing
    input_schema = StructType([
        StructField("product_id", StringType(), True), # Nullable for this test input
        StructField("category", StringType(), True),
        StructField("sub_category", StringType(), True),
        StructField("product_name", StringType(), True),
        StructField("state", StringType(), True),
        StructField("price_per_product", DoubleType(), True),
        StructField("file_date", DateType(), False)
    ])

    df_with_nulls = spark_session.createDataFrame(
        [
            ("P001", "Electronics", "Phones", "Smartphone X", "California", 999.99, date(2025, 5, 23)),
            (None, "Office Supplies", "Paper", "Printer Paper", "New York", 25.50, date(2025, 5, 23)), # Null product_id
            ("P003", "Furniture", "Chairs", "Executive Chair", "Texas", 350.00, date(2025, 5, 23)),
        ], schema=input_schema
    )

    reject_folder_base_path = str(tmp_path / "rejected_products_data")

    with patch('pyspark.sql.DataFrame.write') as mock_df_write:
        mock_df_writer_chained_mock = MagicMock()
        mock_df_write.return_value = mock_df_writer_chained_mock
        mock_df_writer_chained_mock.format.return_value = mock_df_writer_chained_mock
        mock_df_writer_chained_mock.mode.return_value = mock_df_writer_chained_mock
        mock_df_writer_chained_mock.option.return_value = mock_df_writer_chained_mock
        mock_df_writer_chained_mock.save.return_value = None

        df_valid = handle_product_id_nulls(
            spark_session,
            df_with_nulls,
            reject_folder_base_path,
            file_date_str,
            mock_dbutils
        )

        assert df_valid.count() == 2, "Expected 2 valid records after handling null product_ids."
        assert df_valid.filter(col("product_id").isNull()).count() == 0, \
            "Valid DataFrame should not contain any records with null 'product_id'."

        valid_product_ids = [row.product_id for row in df_valid.collect()]
        assert "P001" in valid_product_ids
        assert "P003" in valid_product_ids
        assert "Printer Paper" not in [row.product_name for row in df_valid.collect()], \
            "The record for 'Printer Paper' (with null product_id) should not be in the valid DataFrame."

    print("handle_product_id_nulls PASSED.")


def test_clean_and_transform_products_data_nulls(spark_session: SparkSession):
    """
    Tests clean_and_transform_products_data function for handling null values
    in string columns and price_per_product.
    """
    print("\n--- Testing clean_and_transform_products_data_nulls ---")
    
    # Define schema for the input DataFrame (after standardization and null ID handling)
    input_schema = StructType([
        StructField("product_id", StringType(), False),
        StructField("category", StringType(), True),
        StructField("sub_category", StringType(), True),
        StructField("product_name", StringType(), True),
        StructField("state", StringType(), True),
        StructField("price_per_product", DoubleType(), True),
        StructField("file_date", DateType(), False)
    ])

    df_input_for_cleaning = spark_session.createDataFrame(
        [
            ("P001", "Electronics", "Phones", "Smartphone X", "California", 999.99, date(2025, 5, 23)),
            ("P002", None, "Paper", "Printer Paper", "New York", 25.50, date(2025, 5, 23)), # Null category
            ("P003", "Furniture", None, "Executive Chair", "Texas", 350.00, date(2025, 5, 23)), # Null sub_category
            ("P004", "Technology", "Laptops", None, "Florida", 1500.00, date(2025, 5, 23)), # Null product_name
            ("P005", "Books", "Fiction", "Sci-Fi Novel", None, 15.00, date(2025, 5, 23)), # Null state
            ("P006", "Misc", "Other", "Unknown Item", "Unknown", None, date(2025, 5, 23)) # Null price_per_product
        ], schema=input_schema
    )

    cleaned_df = clean_and_transform_products_data(df_input_for_cleaning)

    # Assertions for coalesced values
    assert cleaned_df.filter(col("product_id") == "P002").select("category").first()[0] == "unknown"
    assert cleaned_df.filter(col("product_id") == "P003").select("sub_category").first()[0] == "unknown"
    assert cleaned_df.filter(col("product_id") == "P004").select("product_name").first()[0] == "unknown"
    assert cleaned_df.filter(col("product_id") == "P005").select("state").first()[0] == "unknown"
    assert cleaned_df.filter(col("product_id") == "P006").select("price_per_product").first()[0] == 0.0

    # Ensure valid data remains unchanged
    assert cleaned_df.filter(col("product_id") == "P001").select("product_name").first()[0] == "Smartphone X"
    assert cleaned_df.filter(col("product_id") == "P001").select("price_per_product").first()[0] == 999.99

    print("clean_and_transform_products_data_nulls PASSED.")


@pytest.mark.parametrize(
    "product_id, category, sub_category, product_name, state, price_per_product, expected_issues",
    [
        ("P010", "Electronics", "Phones", "Valid Product", "California", 100.0, []),
        ("P001", "Electronics", "Phones", "Duplicate Product", "California", 100.0, ["PRODUCT_ID_DUPLICATE_IN_BATCH"]),
        ("P011", "Books", "Fiction", "Negative Price Book", "New York", -5.0, ["PRICE_PER_PRODUCT_NEGATIVE"]),
        ("P012", "Office Supplies", "Paper", "unknown", "Texas", 10.0, ["PRODUCT_NAME_IS_UNKNOWN"]),
        ("P013", "Electronics", "Gadgets", "Combined Issues", "Florida", -10.0, ["PRICE_PER_PRODUCT_NEGATIVE"]),
        ("P014", "Electronics", "Gadgets", "unknown", "Florida", -10.0, ["PRICE_PER_PRODUCT_NEGATIVE", "PRODUCT_NAME_IS_UNKNOWN"])
    ]
)
def test_perform_product_data_quality_checks(spark_session: SparkSession,
                                             product_id, category, sub_category, product_name, state, price_per_product,
                                             expected_issues):
    """
    Tests various data quality checks using parameterized inputs for the perform_product_data_quality_checks function.
    """
    print(f"\n--- Testing perform_product_data_quality_checks for product_id: {product_id} ---")

    # Schema for the input to DQ checks (after standardization and cleaning)
    pre_dq_schema = StructType([
        StructField("product_id", StringType(), False),
        StructField("category", StringType(), True),
        StructField("sub_category", StringType(), True),
        StructField("product_name", StringType(), True),
        StructField("state", StringType(), True),
        StructField("price_per_product", DoubleType(), True),
        StructField("file_date", DateType(), False)
    ])

    current_test_data = [(
        product_id, category, sub_category, product_name, state, price_per_product,
        date(2025, 5, 23)
    )]

    # Add a duplicate record if testing for PRODUCT_ID_DUPLICATE_IN_BATCH
    if "PRODUCT_ID_DUPLICATE_IN_BATCH" in expected_issues:
        current_test_data.append((
            product_id, "Duplicate Category", "Duplicate Sub", "Duplicate Product", "Duplicate State", 99.99,
            date(2025, 5, 23)
        ))

    df_for_dq = spark_session.createDataFrame(current_test_data, pre_dq_schema)
    df_with_dq_issues = perform_product_data_quality_checks(df_for_dq)
    
    # Collect all DQ issues for the given product_id
    actual_issues_row = df_with_dq_issues.filter(col("product_id") == product_id).select("dq_issues").collect()

    actual_issues = []
    if actual_issues_row and actual_issues_row[0].dq_issues: # Check if dq_issues list is not None and not empty
        actual_issues.extend(actual_issues_row[0].dq_issues)
    actual_issues = sorted(list(set(actual_issues))) # Ensure unique and sorted

    expected_issues_sorted = sorted(expected_issues)

    assert actual_issues == expected_issues_sorted, \
        f"DQ issues for product_id {product_id} mismatch.\n" \
        f"Expected: {expected_issues_sorted}\n" \
        f"Actual: {actual_issues}"

    print(f"DQ check for product_id {product_id} PASSED. Issues: {actual_issues}")

