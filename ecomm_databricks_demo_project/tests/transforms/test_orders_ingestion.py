import pytest
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import col, lit, current_timestamp, to_date, md5, concat_ws, date_sub, array, array_union, size, round
from pyspark.sql.types import StructType, StructField, StringType, DateType, ArrayType, BooleanType, TimestampType, IntegerType, DoubleType
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch, ANY
import os

# Assuming your ingestion code is in a module named 'ecomm_ingestion_pipeline'
# You might need to adjust this import based on your project structure
from transform_functions.ingest_orders_data_functions import (
    standardize_orders_columns,
    handle_critical_id_nulls,
    clean_and_transform_orders_data,
    perform_order_data_quality_checks,
    load_raw_orders_json,
    orders_schema, # Import the schema for creating test DataFrames
    processed_orders_schema # Not directly used in these unit tests
)


def test_standardize_orders_columns(
    spark_session: SparkSession,
    mock_raw_orders_df: DataFrame # This DF now represents the raw, Camel Case input
):
    """
    Tests standardize_orders_columns function to ensure:
    1. Columns are renamed from Camel Case to snake_case.
    2. 'file_date' column is correctly added and is of DateType.
    """
    print("\n--- Testing standardize_orders_columns ---")

    file_date_str = "2025-05-23"
    expected_file_date = date.fromisoformat(file_date_str)
    print(f"Expected file_date: {expected_file_date}")

    # Call the actual function with the raw (Camel Case) DataFrame
    df_standardized = standardize_orders_columns(mock_raw_orders_df, file_date_str)

    # --- Hardcoded list of expected standardized column names ---
    expected_standardized_columns = [
        "row_id",
        "order_id",
        "order_date",
        "ship_date",
        "ship_mode",
        "customer_id",
        "product_id",
        "quantity",
        "price",
        "discount",
        "profit",
        "file_date"
    ]

    # Assertions
    # 1. Check if all expected snake_case columns are present and no unexpected columns
    assert sorted(df_standardized.columns) == sorted(expected_standardized_columns), \
        f"Standardized columns do not match expected list. Expected: {expected_standardized_columns}, Got: {df_standardized.columns}"

    # 2. Check count of rows (should remain the same)
    assert df_standardized.count() == mock_raw_orders_df.count(), "Row count changed after standardization."

    # 3. Check data type of 'file_date' and its value
    assert "file_date" in df_standardized.columns
    assert df_standardized.schema["file_date"].dataType == DateType(), \
        "file_date column should be of DateType."
    
    # Verify a specific row's data and the file_date
    first_row = df_standardized.filter(col("order_id") == "O1").collect()[0]
    
    assert first_row.customer_id == "C1"
    assert first_row.quantity == 10 # Check a renamed column's data
    assert first_row.file_date == expected_file_date, \
        f"file_date value is incorrect. Expected {expected_file_date}, got {first_row.file_date}"

    print("standardize_orders_columns PASSED.")


def test_handle_critical_id_nulls(
    spark_session: SparkSession,
    mock_dbutils: MagicMock,
    tmp_path
):
    """
    Tests handle_critical_id_nulls function to ensure:
    1. Records with null 'row_id', 'order_id', 'customer_id', or 'product_id' are rejected.
    2. Valid records are returned.
    3. Mocks the file system write operation for rejected records.
    """
    print("\n--- Testing handle_critical_id_nulls ---")

    file_date_str = "2025-05-23" 
    
    # Define a local schema for this test to allow nulls in critical ID columns
    # This allows us to directly test the null handling logic by injecting nulls.
    # NOTE: For this test to be truly effective, the 'orders_schema' in
    # 'ingest_orders_data_functions.py' should define 'Row ID', 'Order ID',
    # 'Customer ID', and 'Product ID' as nullable (True). Otherwise, the
    # load_raw_orders_json function would fail on schema enforcement before
    # handle_critical_id_nulls is called in a real pipeline run.
    test_input_schema_for_null_handling = StructType([
        StructField("row_id", IntegerType(), True), # Allow null for testing
        StructField("order_id", StringType(), True), # Allow null for testing
        StructField("order_date", DateType(), True),
        StructField("ship_date", DateType(), True),
        StructField("ship_mode", StringType(), True),
        StructField("customer_id", StringType(), True), # Allow null for testing
        StructField("product_id", StringType(), True), # Allow null for testing
        StructField("quantity", IntegerType(), True),
        StructField("price", DoubleType(), True),
        StructField("discount", DoubleType(), True),
        StructField("profit", DoubleType(), True),
        StructField("file_date", DateType(), False) # file_date is added by standardize_orders_columns
    ])

    # Create a DataFrame with nulls in critical ID columns for testing
    input_data_with_nulls = [
        (1, "O1", date(2025, 1, 1), date(2025, 1, 5), "Standard", "C1", "P1", 10, 100.0, 0.1, 10.0, date(2025, 5, 23)),
        (None, "O2", date(2025, 1, 2), date(2025, 1, 6), "Fast", "C2", "P2", 5, 50.0, 0.05, 5.0, date(2025, 5, 23)), # Null row_id
        (3, None, date(2025, 1, 3), date(2025, 1, 7), "Same Day", "C3", "P3", 2, 20.0, 0.0, 2.0, date(2025, 5, 23)), # Null order_id
        (4, "O4", date(2025, 1, 4), date(2025, 1, 8), "Standard", None, "P4", 7, 75.0, 0.15, 11.25, date(2025, 5, 23)), # Null customer_id
        (5, "O5", date(2025, 1, 5), date(2025, 1, 9), "Express", "C5", None, 1, 120.0, 0.2, 24.0, date(2025, 5, 23)), # Null product_id
        (6, "O6", date(2025, 1, 10), date(2025, 1, 15), "Standard", "C6", "P6", 3, 30.0, 0.1, 3.0, date(2025, 5, 23)),
    ]

    # Create the DataFrame using the local schema that allows nulls
    df_input_for_null_handling = spark_session.createDataFrame(input_data_with_nulls, schema=test_input_schema_for_null_handling)
    
    reject_folder_base_path = str(tmp_path / "rejected_data")

    # Patch the 'save' method of the DataFrameWriter directly
    with patch('pyspark.sql.DataFrameWriter.save') as mock_save:
        # We don't need to chain mocks for format, mode, option if we only care about save
        # These methods will be called on a real DataFrameWriter object, but their results
        # are discarded as soon as 'save' is called and mocked.

        df_valid = handle_critical_id_nulls(
            spark_session,
            df_input_for_null_handling,
            reject_folder_base_path,
            file_date_str,
            mock_dbutils
        )

        # Assertions
        assert df_valid.count() == 2, "Expected 2 valid records."
        assert df_valid.filter(col("row_id").isNull() | col("order_id").isNull() | \
                                col("customer_id").isNull() | col("product_id").isNull()).count() == 0, \
            "Valid DataFrame should not contain any records with null critical IDs."

        valid_order_ids = [row.order_id for row in df_valid.collect()]
        assert "O1" in valid_order_ids
        assert "O6" in valid_order_ids
        assert "O2" not in valid_order_ids
        assert "O3" not in valid_order_ids
        assert "O4" not in valid_order_ids
        assert "O5" not in valid_order_ids
        

    print("handle_critical_id_nulls PASSED.")


def test_clean_and_transform_orders_data(spark_session: SparkSession):
    """
    Tests clean_and_transform_orders_data function for handling nulls and rounding profit.
    """
    print("\n--- Testing clean_and_transform_orders_data ---")
    
    # Define schema for the input DataFrame (after standardization and null ID handling)
    input_schema = StructType([
        StructField("row_id", IntegerType(), False),
        StructField("order_id", StringType(), False),
        StructField("order_date", DateType(), True),
        StructField("ship_date", DateType(), True),
        StructField("ship_mode", StringType(), True),
        StructField("customer_id", StringType(), False),
        StructField("product_id", StringType(), False),
        StructField("quantity", IntegerType(), True),
        StructField("price", DoubleType(), True),
        StructField("discount", DoubleType(), True),
        StructField("profit", DoubleType(), True),
        StructField("file_date", DateType(), False) # Added file_date to match the number of fields
    ])

    df_input_for_cleaning = spark_session.createDataFrame(
        [
            (1, "O1", date(2025, 1, 1), date(2025, 1, 5), "Standard", "C1", "P1", 10, 100.0, 0.1, 10.123, date(2025, 5, 23)), # Profit to be rounded
            (2, "O2", None, date(2025, 1, 6), "Fast", "C2", "P2", 5, 50.0, 0.05, 5.0, date(2025, 5, 23)), # Null order_date
            (3, "O3", date(2025, 1, 3), None, "Same Day", "C3", "P3", 2, 20.0, 0.0, 2.0, date(2025, 5, 23)), # Null ship_date
            (4, "O4", date(2025, 1, 4), date(2025, 1, 8), None, "C4", "P4", 7, 75.0, 0.15, 11.25, date(2025, 5, 23)), # Null ship_mode
            (5, "O5", date(2025, 1, 5), date(2025, 1, 9), "Express", "C5", "P5", None, 120.0, 0.2, 24.0, date(2025, 5, 23)), # Null quantity
            (6, "O6", date(2025, 1, 10), date(2025, 1, 15), "Standard", "C6", "P6", 3, None, 0.1, 3.0, date(2025, 5, 23)), # Null price
            (7, "O7", date(2025, 1, 11), date(2025, 1, 16), "Standard", "C7", "P7", 4, 40.0, None, 4.0, date(2025, 5, 23)), # Null discount
            (8, "O8", date(2025, 1, 12), date(2025, 1, 17), "Standard", "C8", "P8", 6, 60.0, 0.1, None, date(2025, 5, 23)), # Null profit
        ], schema=input_schema
    )

    cleaned_df = clean_and_transform_orders_data(df_input_for_cleaning)

    # Assertions
    # Check profit rounding
    assert cleaned_df.filter(col("order_id") == "O1").select("profit").first()[0] == 10.12

    # Check null coalescing for dates
    assert cleaned_df.filter(col("order_id") == "O2").select("order_date").first()[0] == date(1900, 1, 1)
    assert cleaned_df.filter(col("order_id") == "O3").select("ship_date").first()[0] == date(1900, 1, 1)

    # Check null coalescing for string
    assert cleaned_df.filter(col("order_id") == "O4").select("ship_mode").first()[0] == "unknown"

    # Check null coalescing for integer
    assert cleaned_df.filter(col("order_id") == "O5").select("quantity").first()[0] == 0

    # Check null coalescing for double
    assert cleaned_df.filter(col("order_id") == "O6").select("price").first()[0] == 0.0
    assert cleaned_df.filter(col("order_id") == "O7").select("discount").first()[0] == 0.0
    assert cleaned_df.filter(col("order_id") == "O8").select("profit").first()[0] == 0.0

    print("clean_and_transform_orders_data PASSED.")

def test_profit_rounding(spark_session: SparkSession):
    """
    Tests that the 'profit' column is correctly rounded to two decimal places
    by the clean_and_transform_orders_data function.
    """
    print("\n--- Testing profit rounding in clean_and_transform_orders_data ---")

    input_schema = StructType([
        StructField("row_id", IntegerType(), False),
        StructField("order_id", StringType(), False),
        StructField("order_date", DateType(), False),
        StructField("ship_date", DateType(), False),
        StructField("ship_mode", StringType(), False),
        StructField("customer_id", StringType(), False),
        StructField("product_id", StringType(), False),
        StructField("quantity", IntegerType(), False),
        StructField("price", DoubleType(), False),
        StructField("discount", DoubleType(), False),
        StructField("profit", DoubleType(), True), # Profit can be null for this test
        StructField("file_date", DateType(), False)
    ])

    test_data = [
        (1, "O_R1", date(2025, 1, 1), date(2025, 1, 2), "Standard", "C1", "P1", 1, 10.0, 0.1, 123.456, date(2025, 5, 23)),
        (2, "O_R2", date(2025, 1, 1), date(2025, 1, 2), "Standard", "C2", "P2", 1, 10.0, 0.1, 78.901, date(2025, 5, 23)),
        (3, "O_R3", date(2025, 1, 1), date(2025, 1, 2), "Standard", "C3", "P3", 1, 10.0, 0.1, 50.000, date(2025, 5, 23)),
        (4, "O_R4", date(2025, 1, 1), date(2025, 1, 2), "Standard", "C4", "P4", 1, 10.0, 0.1, 0.005, date(2025, 5, 23)), # Should round up
        (5, "O_R5", date(2025, 1, 1), date(2025, 1, 2), "Standard", "C5", "P5", 1, 10.0, 0.1, 0.004, date(2025, 5, 23)), # Should round down
        (6, "O_R6", date(2025, 1, 1), date(2025, 1, 2), "Standard", "C6", "P6", 1, 10.0, 0.1, None, date(2025, 5, 23)), # Null profit
    ]

    df_input = spark_session.createDataFrame(test_data, schema=input_schema)
    cleaned_df = clean_and_transform_orders_data(df_input)

    # Collect results for verification
    results = cleaned_df.select("order_id", "profit").collect()
    profit_map = {row.order_id: row.profit for row in results}

    assert profit_map["O_R1"] == 123.46, "Profit for O_R1 not rounded correctly"
    assert profit_map["O_R2"] == 78.90, "Profit for O_R2 not rounded correctly"
    assert profit_map["O_R3"] == 50.00, "Profit for O_R3 not rounded correctly"
    assert profit_map["O_R4"] == 0.01, "Profit for O_R4 not rounded correctly (should round up)"
    assert profit_map["O_R5"] == 0.00, "Profit for O_R5 not rounded correctly (should round down)"
    assert profit_map["O_R6"] == 0.00, "Null profit not coalesced to 0.00"

    print("test_profit_rounding PASSED.")


@pytest.mark.parametrize(
    "row_id, order_id, order_date, ship_date, quantity, price, discount, expected_issues",
    [
        (101, "ORD101", date(2025, 1, 1), date(2025, 1, 5), 10, 100.0, 0.1, []), # Valid
        (102, "ORD102", date(2025, 1, 1), date(2025, 1, 5), -5, 50.0, 0.05, ["QUANTITY_NEGATIVE"]), # Negative quantity
        (103, "ORD103", date(2025, 1, 1), date(2025, 1, 5), 2, -20.0, 0.0, ["PRICE_NEGATIVE"]), # Negative price
        (104, "ORD104", date(2025, 1, 1), date(2025, 1, 5), 7, 75.0, 1.5, ["DISCOUNT_OUT_OF_RANGE"]), # Discount > 1.0
        (105, "ORD105", date(2025, 1, 1), date(2024, 12, 25), 1, 120.0, 0.2, ["SHIP_DATE_BEFORE_ORDER_DATE"]), # Ship date before order date
        (106, "ORD106", date(2025, 1, 1), date(2025, 1, 5), 1, 10.0, -0.1, ["DISCOUNT_OUT_OF_RANGE"]), # Discount < 0.0
        (107, "ORD107", date(2025, 1, 1), date(2025, 1, 5), -1, -10.0, 1.1, # Multiple issues
            ["QUANTITY_NEGATIVE", "PRICE_NEGATIVE", "DISCOUNT_OUT_OF_RANGE"]),
        (108, "ORD108", date(2025, 1, 1), date(2025, 1, 5), 5, 50.0, 0.1, ["ROW_ID_DUPLICATE_IN_BATCH"]), # Duplicate row_id (will add another record with 108)
    ]
)
def test_perform_order_data_quality_checks(spark_session: SparkSession,
                                           row_id, order_id, order_date, ship_date, quantity, price, discount,
                                           expected_issues):
    """
    Tests various data quality checks using parameterized inputs for the perform_order_data_quality_checks function.
    """
    print(f"\n--- Testing perform_order_data_quality_checks for order_id: {order_id} ---")

    # Schema for the input to DQ checks (after standardization and cleaning)
    pre_dq_schema = StructType([
        StructField("row_id", IntegerType(), False),
        StructField("order_id", StringType(), False),
        StructField("order_date", DateType(), False),
        StructField("ship_date", DateType(), False),
        StructField("ship_mode", StringType(), False),
        StructField("customer_id", StringType(), False),
        StructField("product_id", StringType(), False),
        StructField("quantity", IntegerType(), False),
        StructField("price", DoubleType(), False),
        StructField("discount", DoubleType(), False),
        StructField("profit", DoubleType(), False),
        StructField("file_date", DateType(), False)
    ])

    current_test_data = [(
        row_id, order_id, order_date, ship_date, "Standard", "C001", "P001", quantity, price, discount, 10.0,
        date(2025, 5, 23)
    )]

    # Add a duplicate record if testing for ROW_ID_DUPLICATE_IN_BATCH
    if "ROW_ID_DUPLICATE_IN_BATCH" in expected_issues:
        current_test_data.append((
            row_id, "DUP_" + order_id, date(2025, 1, 1), date(2025, 1, 5), "Standard", "C002", "P002", 1, 1.0, 0.0, 1.0,
            date(2025, 5, 23)
        ))

    df_for_dq = spark_session.createDataFrame(current_test_data, pre_dq_schema)
    df_with_dq_issues = perform_order_data_quality_checks(df_for_dq)
    
    # Collect all DQ issues for the given order_id
    actual_issues_row = df_with_dq_issues.filter(col("order_id") == order_id).select("dq_issues").collect()

    actual_issues = []
    if actual_issues_row and actual_issues_row[0].dq_issues: # Check if dq_issues list is not None and not empty
        actual_issues.extend(actual_issues_row[0].dq_issues)
    actual_issues = sorted(list(set(actual_issues))) # Ensure unique and sorted

    expected_issues_sorted = sorted(expected_issues)

    assert actual_issues == expected_issues_sorted, \
        f"DQ issues for order_id {order_id} mismatch.\n" \
        f"Expected: {expected_issues_sorted}\n" \
        f"Actual: {actual_issues}"

    print(f"DQ check for order_id {order_id} PASSED. Issues: {actual_issues}")

