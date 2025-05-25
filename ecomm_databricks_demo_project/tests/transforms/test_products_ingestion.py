import pytest
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, TimestampType, DateType
from pyspark.sql.functions import lit, col, current_timestamp, to_date
from unittest.mock import patch, MagicMock
from datetime import datetime 

from transform_functions.ingest_products_data_functions import (
    load_raw_products_csv,
    standardize_products_columns,
    clean_and_transform_products_data,
    load_products_data,
    ingest_products_pipeline,
    products_schema # Import the schema
)

from common.configurations import raw_folder_path


# --- Unit Tests ---

def test_load_raw_products_csv_success(spark_session: SparkSession, mock_raw_products_df: DataFrame):
    """
    Tests that load_raw_products_csv correctly attempts to read a CSV file
    and returns a DataFrame matching the expected schema and count.
    """
    test_file_date = "2025-05-23"
    expected_load_path = f"{raw_folder_path}/{test_file_date}/Products.csv"

    with patch('pyspark.sql.SparkSession.read') as mock_spark_read:
        mock_format_return = MagicMock()
        mock_option_return = MagicMock()
        mock_schema_return = MagicMock()

        mock_spark_read.format.return_value = mock_format_return
        mock_format_return.option.return_value = mock_option_return
        mock_option_return.schema.return_value = mock_schema_return
        mock_schema_return.load.return_value = mock_raw_products_df

        df = load_raw_products_csv(spark_session, test_file_date, raw_folder_path, products_schema)

        mock_spark_read.format.assert_called_once_with("csv")
        mock_format_return.option.assert_called_once_with("header", "true")
        mock_option_return.schema.assert_called_once_with(products_schema)
        mock_schema_return.load.assert_called_once_with(expected_load_path)

        assert df is mock_raw_products_df
        assert df.count() == mock_raw_products_df.count()
        assert df.count() == 5
        assert df.schema == products_schema


def test_standardize_products_columns(spark_session: SparkSession, mock_raw_products_df: DataFrame):
    """
    Tests if raw product columns are correctly renamed and a file_date column is added.
    """
    test_file_date = "2025-05-23"
    df_renamed = standardize_products_columns(mock_raw_products_df, test_file_date)

    expected_cols = ["product_id", "category", "sub_category", "product_name", "state", "price_per_product", "file_date"]

    assert all(col_name in df_renamed.columns for col_name in expected_cols)
    assert "Product ID" not in df_renamed.columns

    product_name_val = df_renamed.filter(col("product_id") == "P001").select("product_name").collect()[0][0]
    assert product_name_val == "Smartphone X"

    price_val = df_renamed.filter(col("product_id") == "P002").select("price_per_product").collect()[0][0]
    assert price_val == 25.50

    assert df_renamed.filter(col("file_date") == to_date(lit(test_file_date))).count() == df_renamed.count()
    assert df_renamed.schema["file_date"].dataType == DateType()


def test_clean_and_transform_products_data_fillna_price(spark_session: SparkSession):
    """
    Tests if 'price_per_product' NULL values are filled with 0.0.
    This test creates its own input DataFrame with standardized column names
    to isolate the cleaning/fillna logic.
    """
    data = [
        ("P1", "CatA", 10.0),
        ("P2", "CatB", None),
        ("P3", "CatC", 5.0)
    ]
    input_schema_for_cleaning = StructType([
        StructField("product_id", StringType(), False),
        StructField("category", StringType(), True),
        StructField("price_per_product", DoubleType(), True)
    ])
    df_input_for_cleaning = spark_session.createDataFrame(data, schema=input_schema_for_cleaning)

    df_cleaned = clean_and_transform_products_data(df_input_for_cleaning)

    assert df_cleaned.filter(col("product_id") == "P2").select("price_per_product").collect()[0][0] == 0.0
    assert df_cleaned.filter(col("product_id") == "P1").select("price_per_product").collect()[0][0] == 10.0
    assert df_cleaned.filter(col("product_id") == "P3").select("price_per_product").collect()[0][0] == 5.0


def test_load_products_data_saves_to_delta(spark_session: SparkSession):
    """
    Tests if the load_products_data function attempts to save to a Delta table
    with the correct table name and mode, using a mocked DataFrame input.
    """
    target_schema_name = "test_target_schema"

    mock_df_to_save = MagicMock(spec=DataFrame)

    # FIX: Explicitly create a mock for the .write attribute and assign it
    mock_df_write = MagicMock()
    mock_df_to_save.write = mock_df_write

    # Wire up the chain on the *mock_df_write* object
    mock_format_chain = MagicMock()
    mock_mode_chain = MagicMock()
    mock_option_chain = MagicMock() # For the .option() call

    mock_df_write.format.return_value = mock_format_chain
    mock_format_chain.mode.return_value = mock_mode_chain
    mock_mode_chain.option.return_value = mock_option_chain # .mode().option() returns this
    mock_option_chain.saveAsTable.return_value = None # .option().saveAsTable() returns None

    # Call the function under test with the mocked DataFrame
    load_products_data(spark_session, target_schema_name, mock_df_to_save)

    # --- Assertions ---
    # Verify the full chain of calls, starting from mock_df_write
    mock_df_write.format.assert_called_once_with("delta")
    mock_format_chain.mode.assert_called_once_with("overwrite")
    mock_mode_chain.option.assert_called_once_with("overwriteSchema", "true") # This assertion should now pass
    mock_option_chain.saveAsTable.assert_called_once_with(f"{target_schema_name}.products")

@patch('transform_functions.ingest_products_data_functions.load_products_data')
@patch('transform_functions.ingest_products_data_functions.clean_and_transform_products_data')
@patch('transform_functions.ingest_products_data_functions.standardize_products_columns')
@patch('transform_functions.ingest_products_data_functions.load_raw_products_csv')
# Patch add_ingestion_date at its import location within ingest_products_data_functions.py
@patch('transform_functions.ingest_products_data_functions.add_ingestion_date')
def test_ingest_products_pipeline_orchestration(
    mock_add_ingestion_date,
    mock_load_raw_products_csv,
    mock_standardize_products_columns,
    mock_clean_and_transform_products_data,
    mock_load_products_data,
    spark_session: SparkSession,
    mock_raw_products_df: DataFrame
):
    test_file_date = "2025-05-23"
    test_raw_path = "/mnt/landing"

    # Define DF representing output of standardize/clean *before* ingestion_date
    dummy_transformed_df_before_ingestion = spark_session.createDataFrame(
        [("P001_processed", "Electronics", "Phones", 999.99, "2025-05-23")],
        ["product_id", "category", "sub_category", "price_per_product", "file_date"]
    ).withColumn("file_date", to_date(col("file_date")))

    # Configure mock return values
    mock_load_raw_products_csv.return_value = mock_raw_products_df
    # standardize_products_columns will return the dummy_transformed_df_before_ingestion
    mock_standardize_products_columns.return_value = dummy_transformed_df_before_ingestion
    mock_clean_and_transform_products_data.return_value = dummy_transformed_df_before_ingestion

    # Configure add_ingestion_date to actually add the column with a dynamic timestamp
    mock_add_ingestion_date.side_effect = lambda df: df.withColumn("ingestion_date", current_timestamp())

    mock_load_products_data.return_value = None

    # Execute the pipeline
    result_df = ingest_products_pipeline(
        spark=spark_session,
        file_date=test_file_date,
        raw_folder_path=test_raw_path
    )

    # --- Assertions ---
    mock_load_raw_products_csv.assert_called_once_with(
        spark_session, test_file_date, test_raw_path, products_schema
    )
    mock_standardize_products_columns.assert_called_once_with(mock_raw_products_df, test_file_date)
    mock_clean_and_transform_products_data.assert_called_once_with(dummy_transformed_df_before_ingestion)
    mock_add_ingestion_date.assert_called_once_with(dummy_transformed_df_before_ingestion)

    assert mock_load_products_data.call_count == 2

    mock_load_products_data.assert_any_call(spark_session, "raw", mock_standardize_products_columns.return_value)
    mock_load_products_data.assert_any_call(spark_session, "processed", result_df)

    assert "ingestion_date" in result_df.columns
    assert result_df.schema["ingestion_date"].dataType == TimestampType()
    assert result_df.count() == dummy_transformed_df_before_ingestion.count()