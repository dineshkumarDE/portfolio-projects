
import pytest
from pyspark.sql import DataFrame
from pyspark.sql.functions import year, sum, col, broadcast, lit
from datetime import date


from transform_functions.aggregation_functions import ( 
    select_and_repartition_dataframes,
    join_ecomm_data,
    aggregate_profit
)


# --- Helper to create processed mock dataframes (Keep this, it's essential for providing test data) ---
def _create_processed_mock_dfs(spark_session, mock_raw_customer_df, mock_raw_orders_df, mock_raw_products_df):
    """
    Helper function to create standardized (processed-like) mock DataFrames.
    This will serve as the "processed layer" data for your tests.
    """
    df_orders_processed_mock = mock_raw_orders_df.select(
        col("Order Date").alias("order_date"),
        col("Profit").alias("profit"),
        col("Customer ID").alias("customer_id"),
        col("Product ID").alias("product_id")
    ).fillna({"profit": 0.0}) \
    .withColumn("ingestion_date", lit("2025-05-23T10:00:00Z").cast("timestamp"))

    df_customers_processed_mock = mock_raw_customer_df.select(
        col("Customer ID").alias("customer_id"),
        col("Customer Name").alias("customer_name"),
        col("Country").alias("country")
    ).withColumn("ingestion_date", lit("2025-05-23T10:00:00Z").cast("timestamp"))

    df_products_processed_mock = mock_raw_products_df.select(
        col("Product ID").alias("product_id"),
        col("Category").alias("category"),
        col("Sub-Category").alias("sub_category"),
        col("Price per product").alias("price_per_product")
    ).fillna({"price_per_product": 0.0})\
    .withColumn("ingestion_date", lit("2025-05-23T10:00:00Z").cast("timestamp"))


    df_combined_mock_data = df_orders_processed_mock \
        .join(broadcast(df_customers_processed_mock), "customer_id", "inner") \
        .join(broadcast(df_products_processed_mock), "product_id", "inner") \
        .drop("ingestion_date") 


    return {
        "customers": df_customers_processed_mock,
        "orders": df_orders_processed_mock,
        "products": df_products_processed_mock,
        "ecomm_combined_data": df_combined_mock_data
    }


# --- Helper fixture to provide the pre-processed mock DFs for tests ---
@pytest.fixture
def processed_mock_data(spark_session, mock_raw_customer_df, mock_raw_orders_df, mock_raw_products_df):
    return _create_processed_mock_dfs(spark_session, mock_raw_customer_df, mock_raw_orders_df, mock_raw_products_df)


# --- Modified Test Functions ---

def test_initial_data_loading_and_selection(spark_session, processed_mock_data):
    # Retrieve the mock 'processed' DataFrames
    df_customers_processed = processed_mock_data["customers"]
    df_orders_processed = processed_mock_data["orders"]
    df_products_processed = processed_mock_data["products"]

    # Call the actual function under test with mock data
    df_orders_selected, df_customers_selected, df_products_selected = \
        select_and_repartition_dataframes(df_customers_processed, df_orders_processed, df_products_processed)

    # Assertions on columns and counts of the *returned* DataFrames
    assert "order_date" in df_orders_selected.columns
    assert "profit" in df_orders_selected.columns
    assert "customer_id" in df_orders_selected.columns
    assert "product_id" in df_orders_selected.columns
    assert "customer_name" in df_customers_selected.columns
    assert "country" in df_customers_selected.columns
    assert "category" in df_products_selected.columns
    assert "sub_category" in df_products_selected.columns

    # The counts should now directly match your mock data (after selection/repartition, which don't change counts)
    assert df_customers_selected.count() == 6
    assert df_orders_selected.count() == 10
    assert df_products_selected.count() == 6


def test_combined_data_join_logic(spark_session, processed_mock_data):
    # Retrieve the mock 'processed' DataFrames
    df_customers_processed = processed_mock_data["customers"]
    df_orders_processed = processed_mock_data["orders"]
    df_products_processed = processed_mock_data["products"]

    # Prepare inputs for the join function (mimicking previous steps)
    df_orders_partitioned, df_customers_partitioned, df_products_partitioned = \
        select_and_repartition_dataframes(df_customers_processed, df_orders_processed, df_products_processed)

    # Call the actual join function under test with mock data
    df_orders_customers_products_joined = join_ecomm_data(
        df_orders_partitioned,
        df_customers_partitioned,
        df_products_partitioned
    )

    expected_columns = {
        "order_date", "profit", "customer_id", "product_id",
        "customer_name", "country", "category", "sub_category"
    }
    assert set(df_orders_customers_products_joined.columns) == expected_columns

    # Expected count based on your specific mock data and inner join logic: 3
    assert df_orders_customers_products_joined.count() == 3


def test_profit_aggregation_logic(spark_session, processed_mock_data):
    # Use the pre-computed combined mock data directly as input for aggregation
    df_combined_data = processed_mock_data["ecomm_combined_data"]

    # Call the actual aggregation function under test with mock data
    df_profit_agg = aggregate_profit(df_combined_data)

    results_df = df_profit_agg.toPandas()

    # Expected number of distinct groups: 3
    assert len(results_df) == 3

    # Ensure consistent order for assertions
    results_df = results_df.sort_values(by=["order_year", "category", "sub_category", "customer_id"]).reset_index(drop=True)

    # Assert specific aggregated values:
    # Based on your mock data analysis:
    # C001, 2024, Electronics, Phones -> total_profit = 2.0 (from O7)
    # C001, 2025, Electronics, Phones -> total_profit = 3.0 (from O6)
    # C002, 2025, Office Supplies, Paper -> total_profit = 0.0 (from O10, profit was None)

    assert results_df.loc[0, "order_year"] == 2024
    assert results_df.loc[0, "customer_id"] == "C001"
    assert results_df.loc[0, "category"] == "Electronics"
    assert results_df.loc[0, "total_profit"] == 2.0

    assert results_df.loc[1, "order_year"] == 2025
    assert results_df.loc[1, "customer_id"] == "C001"
    assert results_df.loc[1, "category"] == "Electronics"
    assert results_df.loc[1, "total_profit"] == 3.0
    
    assert results_df.loc[2, "order_year"] == 2025
    assert results_df.loc[2, "customer_id"] == "C002"
    assert results_df.loc[2, "category"] == "Office Supplies"
    assert results_df.loc[2, "total_profit"] == 0.0 # From O10 with None profit, sum() returns 0.0 for all-null group