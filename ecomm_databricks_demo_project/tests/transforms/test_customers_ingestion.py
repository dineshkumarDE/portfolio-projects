import pytest
from datetime import datetime, timedelta 
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.types import StructType, StructField, StringType, LongType, IntegerType, DoubleType, DateType, TimestampType
from pyspark.sql.functions import lit, col, year, current_timestamp, to_date
import os
from unittest.mock import patch, MagicMock, ANY 
from transform_functions.ingest_customer_data_functions import customer_column_standardize, clean_customer_data, ingest_customer_pipeline, customer_schema, load_customer_data 

from pyspark.sql.functions import col, lit, date_add 
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
    assert customer_c004_phone == "unknown"
    print("Phone error string handling test PASSED.")


def test_add_ingestion_date_adds_column(spark_session: SparkSession, mock_raw_customer_df):
    """
    Tests if the add_ingestion_date function correctly adds the column.
    """
    print("Applying column standardization and adding file_date.") 
    transformed_df = customer_column_standardize(mock_raw_customer_df, "2025-05-23")
    
    start_time = datetime.now() 
    final_df = add_ingestion_date(transformed_df)
    end_time = datetime.now() 

    assert "ingestion_date" in final_df.columns
    assert final_df.schema["ingestion_date"].dataType == TimestampType()
    assert final_df.filter(col("ingestion_date").isNotNull()).count() == final_df.count()

    # Get the actual ingestion date from the DataFrame
    actual_ingestion_date_spark = final_df.select("ingestion_date").first()[0]
    
    if isinstance(actual_ingestion_date_spark, datetime):
        actual_ingestion_date = actual_ingestion_date_spark
    else:
       
        actual_ingestion_date = actual_ingestion_date_spark 
    assert start_time <= actual_ingestion_date <= end_time + timedelta(seconds=5) 
    print("add_ingestion_date test PASSED.")


# --- End-to-End Pipeline Test (using mocks for external calls) ---

@patch('transform_functions.ingest_customer_data_functions.load_raw_customer_excel') # Mock the external Excel loading
# Patch add_ingestion_date where it is imported within ingest_customer_data_functions
# Assuming ingest_customer_pipeline imports add_ingestion_date from common.functions,
# and ingest_customer_data_functions has `from common.functions import add_ingestion_date`
@patch('transform_functions.ingest_customer_data_functions.add_ingestion_date') 
@patch('transform_functions.ingest_customer_data_functions.load_customer_data') 
def test_ingest_customer_pipeline_success(
    mock_load_customer_data, 
    mock_add_ingestion_date, 
    mock_load_raw_customer_excel, 
    spark_session,
    mock_raw_customer_df 
):
    """
    Tests the full pipeline by mocking external dependencies.
    """
    print(f"Starting customer ingestion pipeline for file date: 2025-05-23")
    test_file_date = "2025-05-23"
    test_raw_path = "/mnt/raw_data_test"

    # Configure the mock to return our mock DataFrame for raw loading
    mock_load_raw_customer_excel.return_value = mock_raw_customer_df

    # Configure mock_add_ingestion_date to add the column dynamically
    mock_add_ingestion_date.side_effect = lambda df: df.withColumn("ingestion_date", current_timestamp())

    mock_load_customer_data.side_effect = lambda spark, schemaname, df: df


    result_df = ingest_customer_pipeline(spark_session, test_file_date, test_raw_path)

    # Assert that the mocked load_raw_customer_excel was called with correct arguments
    mock_load_raw_customer_excel.assert_called_once_with(
        spark_session, test_file_date, test_raw_path, customer_schema
    )
    
    # Assert that add_ingestion_date was called once
    mock_add_ingestion_date.assert_called_once() 

    # Assert that load_customer_data was called twice
    assert mock_load_customer_data.call_count == 2
    
    first_call_df_arg = mock_load_customer_data.call_args_list[0].args[2]
    assert first_call_df_arg.schema.names == customer_column_standardize(mock_raw_customer_df, test_file_date).schema.names
    assert first_call_df_arg.count() == mock_raw_customer_df.count()
    mock_load_customer_data.assert_any_call(spark_session, "raw", ANY) 

    second_call_df_arg = mock_load_customer_data.call_args_list[1].args[2]
    assert second_call_df_arg.schema.names == result_df.schema.names
    assert second_call_df_arg.count() == result_df.count()
    assert "ingestion_date" in second_call_df_arg.columns
    mock_load_customer_data.assert_any_call(spark_session, "processed", ANY) 

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
    expected_date_obj = datetime.strptime(test_file_date, "%Y-%m-%d").date()
    assert file_date_val == expected_date_obj

    ingestion_date_val = result_df.filter(col("customer_id") == "C001").select("ingestion_date").first()[0]

  
    assert isinstance(ingestion_date_val, datetime)

    now = datetime.now()

    assert now - timedelta(seconds=5) <= ingestion_date_val <= now + timedelta(seconds=5)
    
    print("Customer ingestion pipeline completed successfully for file date: 2025-05-23")
    print("Assertion passed for dynamic timestamp!")