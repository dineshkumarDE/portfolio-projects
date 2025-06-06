import pytest
from pyspark.sql import SparkSession,DataFrame
from pyspark.sql.functions import col, lit, current_timestamp, to_date, md5, concat_ws, date_sub
from pyspark.sql.types import StructType, StructField, StringType, DateType, ArrayType, BooleanType, TimestampType
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch, ANY
import os

# Assuming your ingestion code is in a module named 'ecomm_ingestion_pipeline'
# You might need to adjust this import based on your project structure
from transform_functions.ingest_customer_data_functions import (
    customer_column_standardize,
    handle_customer_id_nulls,
    clean_customer_data,
    perform_customer_data_quality_checks,
    load_raw_customer_excel,
    # customer_schema, # Not directly used in these unit tests, but good to have for understanding
    # processed_customer_schema # Not directly used in these unit tests
)

def test_customer_column_standardize(
    spark_session: SparkSession,
    mock_raw_customers_df: DataFrame # This DF now represents the raw, Camel Case input
):
    """
    Tests customer_column_standardize function to ensure:
    1. Columns are renamed from Camel Case to snake_case.
    2. 'file_date' column is correctly added and is of DateType.
    """
    print("\n--- Testing customer_column_standardize ---")

    file_date_str = "2025-05-23"
    expected_file_date = date.fromisoformat(file_date_str)
    #expected_file_date = to_date(lit(file_date_str), "yyyy-MM-dd")
    print(f"Expected file_date: {expected_file_date}")

    # Call the actual function with the raw (Camel Case) DataFrame
    df_standardized = customer_column_standardize(mock_raw_customers_df, file_date_str)

    # --- Hardcoded list of expected standardized column names ---
    expected_standardized_columns = [
        "customer_id",
        "customer_name",
        "email",
        "phone",
        "address",
        "segment",    
        "country",    
        "city",
        "state",
        "postal_code",
        "region",     
        "file_date"
    ]

    # Assertions
    # 1. Check if all expected snake_case columns are present and no unexpected columns
    assert sorted(df_standardized.columns) == sorted(expected_standardized_columns), \
        f"Standardized columns do not match expected list. Expected: {expected_standardized_columns}, Got: {df_standardized.columns}"

    # 2. Check count of rows (should remain the same)
    assert df_standardized.count() == 3, "Row count changed after standardization."

    # 3. Check data type of 'file_date' and its value
    assert "file_date" in df_standardized.columns
    assert df_standardized.schema["file_date"].dataType == DateType(), \
        "file_date column should be of DateType."
    print(df_standardized.show())
    # Verify a specific row's data and the file_date
    first_row = df_standardized.filter(col("customer_id") == "C001").collect()[0]
    
    assert first_row.customer_name == "Alice"
    assert str(first_row.postal_code) == "90210" # Check a renamed column's data
    assert first_row.file_date == expected_file_date, \
        f"file_date value is incorrect. Expected {expected_file_date}, got {first_row.file_date}"

    print("customer_column_standardize PASSED.")


# --- Corrected Test for handle_customer_id_nulls (Option 2 solution) ---
def test_handle_customer_id_nulls(
    spark_session: SparkSession,
    mock_raw_customers_df: DataFrame, # This DF still represents the raw, Camel Case input
    mock_dbutils: MagicMock,
    tmp_path
):
    """
    Tests handle_customer_id_nulls function (Option 2: cannot change function signature)
    to ensure:
    1. Records with null 'customer_id' are correctly excluded from the returned DataFrame.
    (Does NOT assert on reject file creation, only provides mocks to allow execution).
    """
    print("\n--- Testing handle_customer_id_nulls (Option 2) ---")

    file_date_str = "2025-05-23" 
    df_standardized_with_nulls = customer_column_standardize(mock_raw_customers_df, file_date_str)

    # Now, pass this standardized DataFrame (which has the null 'customer_id')
    # directly to the handle_customer_id_nulls function.
    reject_folder_base_path = str(tmp_path / "rejected_data")

    with patch('pyspark.sql.DataFrame.write') as mock_df_write:
        mock_df_writer_chained_mock = MagicMock()
        mock_df_write.return_value = mock_df_writer_chained_mock
        mock_df_writer_chained_mock.format.return_value = mock_df_writer_chained_mock
        mock_df_writer_chained_mock.mode.return_value = mock_df_writer_chained_mock
        mock_df_writer_chained_mock.option.return_value = mock_df_writer_chained_mock
        mock_df_writer_chained_mock.save.return_value = None

        df_valid = handle_customer_id_nulls(
            spark_session,
            df_standardized_with_nulls, # Use the DataFrame that *simulates the pipeline flow*
            reject_folder_base_path,
            file_date_str,
            mock_dbutils
        )

        assert df_valid.count() == 2, "Expected 2 valid records."
        assert df_valid.filter(col("customer_id").isNull()).count() == 0, \
            "Valid DataFrame should not contain any records with null 'customer_id'."

        valid_customer_ids = [row.customer_id for row in df_valid.collect()]
        assert "C001" in valid_customer_ids
        assert "C003" in valid_customer_ids
        assert "Bob" not in [row.customer_name for row in df_valid.collect()], \
            "The record for 'Bob' (with null customer_id) should not be in the valid DataFrame."

    print("handle_customer_id_nulls PASSED.")

def test_clean_customer_data_nulls_and_error_strings(spark_session: SparkSession):
    """
    Tests clean_customer_data function for handling null customer names and phone error strings.
    """
    print("\n--- Testing clean_customer_data_nulls_and_error_strings ---")
    
    # Define schema for the input DataFrame
    input_schema = StructType([
        StructField("customer_id", StringType(), False), # Assuming customer_id is non-nullable after handle_nulls
        StructField("customer_name", StringType(), True),
        StructField("email", StringType(), True),
        StructField("phone", StringType(), True),
        StructField("file_date", DateType(), False)
    ])

    df_input_for_cleaning = spark_session.createDataFrame(
        [
            ("C001", "Alice", "alice@example.com", "123-456-7890", date(2025, 5, 23)),
            ("C002", "Bob", "bob@example.com", "#ERROR!", date(2025, 5, 23)), # Error string for phone
            ("C003", None, "charlie@example.com", "789-012-3456", date(2025, 5, 23)), # Null customer name
            ("C004", "David", "david@example.com", None, date(2025, 5, 23)) # Null phone
        ], schema=input_schema
    )

    cleaned_df = clean_customer_data(df_input_for_cleaning)

    # Assert that the null customer name (for C003) has been coalesced to "unknown"
    assert cleaned_df.filter(col("customer_id") == "C003").select("customer_name").first()[0] == "unknown"
    # Assert that the phone number with "#ERROR!" (for C002) has been replaced with "unknown"
    assert cleaned_df.filter(col("customer_id") == "C002").select("phone").first()[0] == "unknown"
    # Assert that the null phone for C004 is also 'unknown'
    assert cleaned_df.filter(col("customer_id") == "C004").select("phone").first()[0] == "unknown"
    
    # Ensure valid data remains unchanged
    assert cleaned_df.filter(col("customer_id") == "C001").select("customer_name").first()[0] == "Alice"
    assert cleaned_df.filter(col("customer_id") == "C001").select("phone").first()[0] == "123-456-7890"

    print("clean_customer_data_nulls_and_error_strings PASSED.")


@pytest.mark.parametrize(
    "customer_id, email, phone, postal_code, customer_name, expected_issues",
    [
        ("C010", "test@example.com", "1234567890", "12345", "Valid Customer", []),
        ("C001", "another@example.com", "9876543210", "54321", "Another Alice", ["CUSTOMER_ID_DUPLICATE_IN_BATCH"]),
        ("C011", "invalid-email", "1234567890", "12345", "Invalid Email User", ["EMAIL_INVALID_FORMAT"]),
        ("C012", "user@.com", "1234567890", "12345", "Invalid Email User 2", ["EMAIL_INVALID_FORMAT"]),
        ("C013", "test@example.com", "abc", "12345", "Invalid Phone User", ["PHONE_INVALID_FORMAT"]),
        ("C014", "test@example.com", "", "12345", "Invalid Phone User 2", ["PHONE_INVALID_FORMAT"]),
        ("C015", "test@example.com", "1234567890", "XYZ", "Invalid Postal User", ["POSTAL_CODE_INVALID_FORMAT"]),
        ("C016", "test@example.com", "1234567890", "123A4", "Invalid Postal User 2", ["POSTAL_CODE_INVALID_FORMAT"]),
        ("C017", "test@example.com", "1234567890", "12345", "unknown", ["CUSTOMER_NAME_IS_UNKNOWN"]),
        ("C018", "bad-email", "bad-phone", "bad-zip", "unknown",
         ["EMAIL_INVALID_FORMAT", "PHONE_INVALID_FORMAT", "POSTAL_CODE_INVALID_FORMAT", "CUSTOMER_NAME_IS_UNKNOWN"]),
        # Corrected expected issues for "unknown" values, assuming DQ flags them
        ("C019", "unknown", "unknown", "unknown", "John Doe",
         ["EMAIL_INVALID_FORMAT", "PHONE_INVALID_FORMAT", "POSTAL_CODE_INVALID_FORMAT"])
    ]
)
def test_perform_customer_data_quality_checks(spark_session: SparkSession,
                                               customer_id, email, phone, postal_code, customer_name,
                                               expected_issues):
    """
    Tests various data quality checks using parameterized inputs for the perform_customer_data_quality_checks function.
    """
    print(f"\n--- Testing perform_customer_data_quality_checks for customer_id: {customer_id} ---")

    # Schema for the input to DQ checks (after standardization and cleaning)
    pre_dq_schema = StructType([
        StructField("customer_id", StringType(), False),
        StructField("customer_name", StringType(), True),
        StructField("email", StringType(), True),
        StructField("phone", StringType(), True),
        StructField("address", StringType(), True),
        StructField("segment", StringType(), True),
        StructField("country", StringType(), True),
        StructField("city", StringType(), True),
        StructField("state", StringType(), True),
        StructField("postal_code", StringType(), True),
        StructField("region", StringType(), True),
        StructField("file_date", DateType(), False)
    ])

    current_test_data = [(
        customer_id, customer_name, email, phone, "address", "segment", "country", "city", "state", postal_code, "region",
        date(2025, 5, 23)
    )]

    # Add a duplicate record if testing for CUSTOMER_ID_DUPLICATE_IN_BATCH
    if "CUSTOMER_ID_DUPLICATE_IN_BATCH" in expected_issues:
        current_test_data.append((
            customer_id, "Duplicate " + customer_name, "dup_" + email, "9999999999", "Dup Address", "Consumer", "USA", "Dup City", "DS", "99999", "Dup Region",
            date(2025, 5, 23)
        ))

    df_for_dq = spark_session.createDataFrame(current_test_data, pre_dq_schema)
    df_with_dq_issues = perform_customer_data_quality_checks(df_for_dq)
    
    # Collect all DQ issues for the given customer_id
    actual_issues_row = df_with_dq_issues.filter(col("customer_id") == customer_id).select("dq_issues").collect()

    actual_issues = []
    if actual_issues_row and actual_issues_row[0].dq_issues: # Check if dq_issues list is not None and not empty
        actual_issues.extend(actual_issues_row[0].dq_issues)
    actual_issues = sorted(list(set(actual_issues))) # Ensure unique and sorted

    expected_issues_sorted = sorted(expected_issues)

    assert actual_issues == expected_issues_sorted, \
        f"DQ issues for customer_id {customer_id} mismatch.\n" \
        f"Expected: {expected_issues_sorted}\n" \
        f"Actual: {actual_issues}"

    print(f"DQ check for customer_id {customer_id} PASSED. Issues: {actual_issues}")

