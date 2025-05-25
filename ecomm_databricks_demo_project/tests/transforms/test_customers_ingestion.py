# Databricks notebook source

import pytest
from datetime import datetime, timedelta 
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.types import StructType, StructField, StringType, LongType, IntegerType, DoubleType, DateType, TimestampType
from pyspark.sql.functions import lit, col, year, current_timestamp, to_date
import os
from unittest.mock import patch, MagicMock, ANY # <--- ADDED: ANY for flexible DataFrame comparisons
# Importing the actual functions from your source module (assuming its path)
from transform_functions.ingest_customer_data_functions import customer_column_standardize, clean_customer_data, ingest_customer_pipeline, customer_schema, load_customer_data # <--- ADDED: load_customer_data for mocking
# The line below is not directly used in this test file's functions, but if you're importing it,
# it might be for a fixture or another test. If not used, it's harmless but could be removed.
from pyspark.sql.functions import col, lit, date_add 
# The common.functions.add_ingestion_date is explicitly imported here.
# For patching, it's often safer to patch where it's *used* in the pipeline module,
# not where it's imported in the test. We'll adjust the patch accordingly.
from common.functions import add_ingestion_date 

# --- Unit Tests ---

def test_transform_customer_data_renames_columns(spark_session: SparkSession, mock_raw_customer_df):
    """
    Tests if columns are correctly renamed and file_date is added.
    """
    print("Applying column standardization and adding file_date.") # Print for clarity
    test_file_date = "2025-05-23"
    transformed_df = customer_column_standardize(mock_raw_customer_df, test_file_date)

    # Check if expected columns exist and old columns are gone
    expected_columns = [
        "customer_id", "customer_name", "email", "phone", "address",
        "segment", "country", "city", "state", "postal_code", "region", "file_date"
    ]
    assert all(col_name in transformed_df.columns for col_name in expected_columns)
    assert "Customer ID" not in transformed_df.columns # Check old column is gone

    # Check if 'file_date' column has the correct value and type
    assert transformed_df.filter(col("file_date") == to_date(lit(test_file_date))).count() == transformed_df.count()
    assert transformed_df.schema["file_date"].dataType == DateType()
    print("Column standardization and file_date test PASSED.")


def test_clean_customer_data_handles_null_customer_name(spark_session: SparkSession, mock_raw_customer_df):
    """
    Tests if 'Customer Name' (now customer_name) NULLs are coalesced to 'unknown'.
    """
    print("Applying column standardization and adding file_date.") # Print for clarity
    # First, apply the rename transformation to get 'customer_name'
    transformed_df = customer_column_standardize(mock_raw_customer_df, "2025-05-23")
    print("Applying data cleaning for customer_name and phone.") # Print for clarity
    cleaned_df = clean_customer_data(transformed_df)

    # Check the row where original 'Customer Name' was None
    # We know C003 had None
    customer_c003 = cleaned_df.filter(col("customer_id") == "C003").select("customer_name").first()[0]
    assert customer_c003 == "unknown"

    # Check that non-null names are unchanged
    customer_c001 = cleaned_df.filter(col("customer_id") == "C001").select("customer_name").first()[0]
    assert customer_c001 == "Alice Smith"
    print("Null customer name handling test PASSED.")


def test_clean_customer_data_handles_phone_error_string(spark_session: SparkSession, mock_raw_customer_df):
    """
    Tests if 'phone' values "#ERROR!" are replaced with 'unknown'.
    """
    print("Applying column standardization and adding file_date.") # Print for clarity
    # First, apply the rename transformation to get 'phone'
    transformed_df = customer_column_standardize(mock_raw_customer_df, "2025-05-23")
    print("Applying data cleaning for customer_name and phone.") # Print for clarity
    cleaned_df = clean_customer_data(transformed_df)

    # Check the row where original 'phone' was "#ERROR!" (C002)
    customer_c002_phone = cleaned_df.filter(col("customer_id") == "C002").select("phone").first()[0]
    assert customer_c002_phone == "unknown"

    # Check that other phone numbers are unchanged
    customer_c001_phone = cleaned_df.filter(col("customer_id") == "C001").select("phone").first()[0]
    assert customer_c001_phone == "123-456-7890"

    # Check that null phone numbers are unchanged (not handled by this specific coalesce)
    customer_c004_phone = cleaned_df.filter(col("customer_id") == "C004").select("phone").first()[0]
    assert customer_c004_phone is None
    print("Phone error string handling test PASSED.")


def test_add_ingestion_date_adds_column(spark_session: SparkSession, mock_raw_customer_df):
    """
    Tests if the add_ingestion_date function correctly adds the column.
    """
    print("Applying column standardization and adding file_date.") # Print for clarity
    # Use a dummy DataFrame (transformed) to test add_ingestion_date
    transformed_df = customer_column_standardize(mock_raw_customer_df, "2025-05-23")
    
    # Capture time *before* calling the function
    start_time = datetime.now() 
    final_df = add_ingestion_date(transformed_df)
    end_time = datetime.now() 

    assert "ingestion_date" in final_df.columns
    assert final_df.schema["ingestion_date"].dataType == TimestampType()
    assert final_df.filter(col("ingestion_date").isNotNull()).count() == final_df.count()

    # Get the actual ingestion date from the DataFrame, converting if necessary
    actual_ingestion_date_spark = final_df.select("ingestion_date").first()[0]
    # Spark TimestampType objects can sometimes be java.sql.Timestamp or Python datetime.
    # For robust comparison, ensure it's a Python datetime.
    if isinstance(actual_ingestion_date_spark, datetime):
        actual_ingestion_date = actual_ingestion_date_spark
    else:
        # If it's a Spark Timestamp object (e.g., java.sql.Timestamp), convert it
        # This conversion might vary based on your Spark setup.
        # A common way is to cast to string and then parse, or assume PySpark handles it well.
        # For this test, given current_timestamp() is from PySpark, direct comparison should work.
        actual_ingestion_date = actual_ingestion_date_spark # Trusting Spark's conversion in test environment

    # Ensure the captured timestamp is within a reasonable window of the test execution
    # Added a small buffer (e.g., 5 seconds) to account for execution time
    assert start_time <= actual_ingestion_date <= end_time + timedelta(seconds=5) # <--- Corrected the comparison for actual_ingestion_date
    print("add_ingestion_date test PASSED.")


# --- End-to-End Pipeline Test (using mocks for external calls) ---

@patch('transform_functions.ingest_customer_data_functions.load_raw_customer_excel') # Mock the external Excel loading
# <--- IMPORTANT PATCH PATH CHANGE HERE ---
# Patch add_ingestion_date where it is imported within ingest_customer_data_functions
# Assuming ingest_customer_pipeline imports add_ingestion_date from common.functions,
# and ingest_customer_data_functions has `from common.functions import add_ingestion_date`
@patch('transform_functions.ingest_customer_data_functions.add_ingestion_date') # <--- CORRECTED PATCH PATH
@patch('transform_functions.ingest_customer_data_functions.load_customer_data') # <--- ADDED: Patch load_customer_data
def test_ingest_customer_pipeline_success(
    mock_load_customer_data, # NEW: This argument for the patched load_customer_data
    mock_add_ingestion_date, 
    mock_load_raw_customer_excel, 
    spark_session,
    mock_raw_customer_df 
):
    """
    Tests the full pipeline by mocking external dependencies.
    """
    print(f"Starting customer ingestion pipeline for file date: 2025-05-23") # Print for clarity
    test_file_date = "2025-05-23"
    test_raw_path = "/mnt/raw_data_test"

    # Configure the mock to return our mock DataFrame for raw loading
    mock_load_raw_customer_excel.return_value = mock_raw_customer_df

    # Configure mock_add_ingestion_date to add the column dynamically
    mock_add_ingestion_date.side_effect = lambda df: df.withColumn("ingestion_date", current_timestamp())

    # Configure mock_load_customer_data to just return the DataFrame it was given
    # This simulates the behavior of your actual load_customer_data function
    mock_load_customer_data.side_effect = lambda spark, schemaname, df: df


    result_df = ingest_customer_pipeline(spark_session, test_file_date, test_raw_path)

    # Assert that the mocked load_raw_customer_excel was called with correct arguments
    mock_load_raw_customer_excel.assert_called_once_with(
        spark_session, test_file_date, test_raw_path, customer_schema
    )
    
    # Assert that add_ingestion_date was called once
    mock_add_ingestion_date.assert_called_once() # We expect it to be called with a DataFrame, but not checking exact content here

    # Assert that load_customer_data was called twice
    assert mock_load_customer_data.call_count == 2
    
    # Assert the first call to load_customer_data (saving to 'raw')
    # The pipeline passes `df_renamed` to raw load, which is a transformed version of `mock_raw_customer_df`
    # Use ANY for the DataFrame argument if the exact instance can vary after Spark operations.
    # Alternatively, you could construct the expected DataFrame here based on `customer_column_standardize`
    # For a robust check, you might check call arguments more generally or schema.
    # Given the pipeline structure, the first call should be with `df_renamed`
    # which is the output of `customer_column_standardize(mock_raw_customer_df, test_file_date)`
    first_call_df_arg = mock_load_customer_data.call_args_list[0].args[2]
    assert first_call_df_arg.schema.names == customer_column_standardize(mock_raw_customer_df, test_file_date).schema.names
    assert first_call_df_arg.count() == mock_raw_customer_df.count()
    mock_load_customer_data.assert_any_call(spark_session, "raw", ANY) # More flexible assertion

    # Assert the second call to load_customer_data (saving to 'processed')
    # This call should use the final `result_df`
    second_call_df_arg = mock_load_customer_data.call_args_list[1].args[2]
    assert second_call_df_arg.schema.names == result_df.schema.names
    assert second_call_df_arg.count() == result_df.count()
    assert "ingestion_date" in second_call_df_arg.columns
    mock_load_customer_data.assert_any_call(spark_session, "processed", ANY) # More flexible assertion

    # Assertions on the final DataFrame structure and data
    expected_final_columns = [
        "customer_id", "customer_name", "email", "phone", "address",
        "segment", "country", "city", "state", "postal_code", "region",
        "file_date", "ingestion_date"
    ]
    assert all(col_name in result_df.columns for col_name in expected_final_columns)
    assert result_df.count() == mock_raw_customer_df.count() 

    # Verify specific transformations
    c003_name = result_df.filter(col("customer_id") == "C003").select("customer_name").first()[0]
    assert c003_name == "unknown"

    c002_phone = result_df.filter(col("customer_id") == "C002").select("phone").first()[0]
    assert c002_phone == "unknown"

    file_date_val = result_df.filter(col("customer_id") == "C001").select("file_date").first()[0]
    assert file_date_val == to_date(lit(test_file_date))

    ingestion_date_val = result_df.filter(col("customer_id") == "C001").select("ingestion_date").first()[0]

    # Assertion 1: Check type - use TimestampType().pythonClass for Python datetime object
    assert isinstance(ingestion_date_val, datetime)
    
    # Assertion 2: Check freshness of the ingestion date (within a short window)
    now = datetime.now()
    # It's better to ensure ingestion_date_val is a Python datetime before subtraction.
    # If it's a PySpark TimestampType.pythonClass, it usually behaves like a datetime.
    assert now - timedelta(seconds=5) <= ingestion_date_val <= now + timedelta(seconds=5) # <--- Refined freshness check
    
    print("Customer ingestion pipeline completed successfully for file date: 2025-05-23")
    print("Assertion passed for dynamic timestamp!") # This print statement was already there.