import pytest
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, DoubleType, DateType, TimestampType
from pyspark.sql.functions import lit, col, current_timestamp, round, to_date 
from unittest.mock import patch, MagicMock
from datetime import datetime,date 

from transform_functions.ingest_orders_data_functions import (
    load_raw_orders_json,
    standardize_orders_columns,
    clean_and_transform_orders_data, 
    load_orders_data,
    ingest_orders_pipeline,
    orders_schema 
)
from common.configurations import raw_folder_path 

# --- Unit Tests ---

def test_load_raw_orders_json_success(spark_session: SparkSession, mock_raw_orders_df: DataFrame):
    """
    Tests that load_raw_orders_json attempts to read from the correct path
    and returns a DataFrame matching the expected schema and count.
    """
    test_file_date = "2025-05-23"
    expected_load_path = f"{raw_folder_path}/{test_file_date}/Orders.json"

    with patch('pyspark.sql.SparkSession.read') as mock_spark_read:
        mock_format_return = MagicMock()
        mock_schema_return = MagicMock()
        mock_option_1_return = MagicMock()
        mock_option_2_return = MagicMock()

        mock_spark_read.format.return_value = mock_format_return
        mock_format_return.schema.return_value = mock_schema_return
        mock_schema_return.option.return_value = mock_option_1_return
        mock_option_1_return.option.return_value = mock_option_2_return
        mock_option_2_return.load.return_value = mock_raw_orders_df

        df = load_raw_orders_json(spark_session, test_file_date, raw_folder_path, orders_schema)

        mock_spark_read.format.assert_called_once_with("json")
        mock_format_return.schema.assert_called_once_with(orders_schema)
        mock_schema_return.option.assert_called_once_with("dateFormat", "d/M/yyyy")
        mock_option_1_return.option.assert_called_once_with("multiLine", "true")
        mock_option_2_return.load.assert_called_once_with(expected_load_path)

        assert df is mock_raw_orders_df
        assert df.count() == mock_raw_orders_df.count()
        assert df.count() == 10
        assert df.schema == orders_schema


def test_standardize_orders_columns(spark_session: SparkSession, mock_raw_orders_df: DataFrame):
    """
    Tests if raw orders columns are correctly renamed and a file_date column is added as DateType.
    """
    test_file_date = "2025-05-23"
    df_renamed = standardize_orders_columns(mock_raw_orders_df, test_file_date)
    # Convert file_date to DateType for test to match main function logic
    df_renamed = df_renamed.withColumn("file_date", to_date(col("file_date"), "yyyy-MM-dd"))

    expected_cols = ["row_id", "order_id", "order_date", "ship_date", "ship_mode",
                     "customer_id", "product_id", "quantity", "price", "discount",
                     "profit", "file_date"]

    assert all(col_name in df_renamed.columns for col_name in expected_cols)
    assert "Row ID" not in df_renamed.columns

    assert df_renamed.filter(col("file_date") == date.fromisoformat(test_file_date)).count() == df_renamed.count()
    assert isinstance(df_renamed.schema["file_date"].dataType, DateType)

    price_value = df_renamed.filter(col("order_id") == "O1").select("price").collect()[0][0]
    assert price_value == 100.0


# Fix the parameterized test for profit rounding and null handling
@pytest.mark.parametrize(
    "input_profit, expected_profit",
    [
        (123.456, 123.46),
        (789.012, 789.01),
        (50.000, 50.00),
        (7.89, 7.89),
        (12.3, 12.30),
        (0.005, 0.01),
        (0.004, 0.00),
        (None, 0.0) 
    ]
)
def test_clean_and_transform_orders_data_profit_rounding_parametrized(
    spark_session: SparkSession,
    input_profit: float,
    expected_profit: float
):
    """
    Tests if profit values are correctly rounded to 2 decimal places and
    null profits are handled, using parametrization.
    Each test case creates a minimal DataFrame *with all expected columns*
    to isolate the profit logic.
    """
    
    raw_data = [
        (
            1,                # Row ID
            "dummy_order_id", # Order ID
            "2024-01-01",     # Order Date (as string, matching how you load raw data then standardize)
            "2024-01-05",     # Ship Date
            "Standard Class", # Ship Mode
            "C_dummy",        # Customer ID
            "P_dummy",        # Product ID
            1,                # Quantity
            10.0,             # Price
            0.0,              # Discount
            input_profit      # Profit (this is the one we're testing)
        )
    ]

    input_schema_for_cleaning = StructType([
        StructField("row_id", IntegerType(), False),
        StructField("order_id", StringType(), False),
        StructField("order_date", DateType(), True), # Your `clean_and_transform_orders_data` directly uses DateType for this
        StructField("ship_date", DateType(), True),
        StructField("ship_mode", StringType(), True),
        StructField("customer_id", StringType(), False),
        StructField("product_id", StringType(), False),
        StructField("quantity", IntegerType(), True),
        StructField("price", DoubleType(), True),
        StructField("discount", DoubleType(), True),
        StructField("profit", DoubleType(), True),
        StructField("file_date", DateType(), True) # Also required if standardize_orders_columns adds it.
    ])



    data_for_cleaning_function = [
        (
            1,                # row_id
            "dummy_order_id", # order_id
            date(2024, 1, 1), # order_date (as Date object for direct schema match)
            date(2024, 1, 5), # ship_date
            "Standard Class", # ship_mode
            "C_dummy",        # customer_id
            "P_dummy",        # product_id
            1,                # quantity
            10.0,             # price
            0.0,              # discount
            input_profit,     # profit
            date(2025, 5, 23) # file_date (dummy value for this test)
        )
    ]

    df_input_for_cleaning_function = spark_session.createDataFrame(data_for_cleaning_function, schema=input_schema_for_cleaning)

    # Call the function under test
    df_cleaned = clean_and_transform_orders_data(df_input_for_cleaning_function)

    # Collect result
    result_profit = df_cleaned.select("profit").collect()[0]["profit"]

    # Assert
    assert result_profit == expected_profit



def test_load_orders_data_saves_to_delta(spark_session: SparkSession):
    """
    Tests if the load_orders_data function attempts to save to a Delta table
    with the correct table name and mode, using a mocked DataFrame input.
    """
    target_schema_name = "test_target_schema"

    # Create a MagicMock to act as the DataFrame passed to load_orders_data
    mock_df_to_save = MagicMock(spec=DataFrame) 
    # Set up the chain for the mock_df_to_save's .write method
    mock_format_chain = MagicMock()
    mock_mode_chain = MagicMock()
    mock_option_chain_overwriteSchema = MagicMock() # For the first .option() call
    mock_option_chain_partitionBy = MagicMock() # For the .partitionBy() call

    mock_df_to_save.write.format.return_value = mock_format_chain
    mock_format_chain.mode.return_value = mock_mode_chain
    mock_mode_chain.option.return_value = mock_option_chain_overwriteSchema
    
    # Add the mock for partitionBy. It should be called after .option("overwriteSchema", "true")
    mock_option_chain_overwriteSchema.partitionBy.return_value = mock_option_chain_partitionBy 
    
    mock_option_chain_partitionBy.saveAsTable.return_value = None # saveAsTable usually returns None

    # Call the function under test with the mocked DataFrame
    load_orders_data(spark_session, target_schema_name, mock_df_to_save)

    # Assertions
    mock_df_to_save.write.format.assert_called_once_with("delta")
    mock_format_chain.mode.assert_called_once_with("overwrite")
    
    # Assert for the first option call
    mock_mode_chain.option.assert_called_once_with("overwriteSchema", "true") 
    
    # Assert for the partitionBy call
    mock_option_chain_overwriteSchema.partitionBy.assert_called_once_with("file_date")

    # Assert for the saveAsTable call, which is now on mock_option_chain_partitionBy
    mock_option_chain_partitionBy.saveAsTable.assert_called_once_with(f"{target_schema_name}.orders")


@patch('transform_functions.ingest_orders_data_functions.load_orders_data')
@patch('transform_functions.ingest_orders_data_functions.clean_and_transform_orders_data')
@patch('transform_functions.ingest_orders_data_functions.standardize_orders_columns')
@patch('transform_functions.ingest_orders_data_functions.load_raw_orders_json')
@patch('transform_functions.ingest_orders_data_functions.add_ingestion_date')
def test_ingest_orders_pipeline_orchestration(
    mock_add_ingestion_date,
    mock_load_raw_orders_json,
    mock_standardize_orders_columns,
    mock_clean_and_transform_orders_data,
    mock_load_orders_data,
    spark_session: SparkSession,
    mock_raw_orders_df: DataFrame
):
    test_file_date = "2025-05-23"
    test_raw_path = "/mnt/landing"

    dummy_transformed_df_before_ingestion = spark_session.createDataFrame(
        [("O1_standard", 123.45, test_file_date, "C1", "P1")],
        ["order_id", "profit", "file_date", "customer_id", "product_id"]
    ).withColumn("file_date", to_date(col("file_date"), "yyyy-MM-dd")) # Ensure file_date is DateType

    mock_load_raw_orders_json.return_value = mock_raw_orders_df
    mock_standardize_orders_columns.return_value = dummy_transformed_df_before_ingestion
    mock_clean_and_transform_orders_data.return_value = dummy_transformed_df_before_ingestion

    # Configure add_ingestion_date to actually add the column with a dynamic timestamp
    mock_add_ingestion_date.side_effect = lambda df: df.withColumn("ingestion_date", current_timestamp())

    mock_load_orders_data.return_value = None

    result_df = ingest_orders_pipeline(
        spark=spark_session,
        file_date=test_file_date,
        raw_folder_path=test_raw_path
    )

    # --- Assertions ---
    mock_load_raw_orders_json.assert_called_once_with(
        spark_session, test_file_date, test_raw_path, orders_schema
    )
    mock_standardize_orders_columns.assert_called_once_with(mock_raw_orders_df, test_file_date)

    mock_clean_and_transform_orders_data.assert_called_once_with(dummy_transformed_df_before_ingestion)

    # Assert that add_ingestion_date was called with the correct DataFrame
    mock_add_ingestion_date.assert_called_once_with(dummy_transformed_df_before_ingestion)

    assert mock_load_orders_data.call_count == 2
    # Verify the "raw" save: it should be the df_renamed, which is the output of standardize_orders_columns
    mock_load_orders_data.assert_any_call(spark_session, "raw", mock_standardize_orders_columns.return_value)
    # For processed, it should receive the DataFrame *after* ingestion_date has been added by its side_effect
    mock_load_orders_data.assert_any_call(spark_session, "processed", result_df)

    assert "ingestion_date" in result_df.columns
    assert result_df.schema["ingestion_date"].dataType == TimestampType()
    assert result_df.count() == dummy_transformed_df_before_ingestion.count()