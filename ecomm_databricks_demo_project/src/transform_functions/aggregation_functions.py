from pyspark.sql import DataFrame
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, DateType, ArrayType, BooleanType # Added BooleanType for is_current
from pyspark.sql.functions import year, sum, col, broadcast, size, lit, count
import logging

# Assume app_logger is initialized externally as "EcommIngestionPipeline"
app_logger = logging.getLogger("EcommIngestionPipeline")
# Ensure app_logger is initialized with handlers (console, file) in your main script
# before calling the aggregation pipeline, otherwise logs will not be written to file.

def select_and_repartition_dataframes(
    df_customers_processed: DataFrame,
    df_orders_processed: DataFrame,
    df_products_processed: DataFrame
) -> (DataFrame, DataFrame, DataFrame):
    """
    Selects required columns, filters out records with data quality issues and
    ensures only current (is_current = true) records are used, then repartitions dataframes.
    Assumes input DataFrames are the 'processed' layer DataFrames, which include
    'dq_issues' and SCD Type 2 columns ('is_current').
    
    Args:
        df_customers_processed (DataFrame): Processed customers DataFrame.
        df_orders_processed (DataFrame): Processed orders DataFrame.
        df_products_processed (DataFrame): Processed products DataFrame.

    Returns:
        tuple: A tuple containing the selected and repartitioned DataFrames
               (df_orders_partitioned, df_customers_partitioned, df_products_partitioned).

    Raises:
        Exception: If any error occurs during selection, filtering, or repartitioning.
    """
    try:
        app_logger.info("Starting selection, data quality filtering, SCD Type 2 filtering, and repartitioning of DataFrames.")

        # Filter out records with data quality issues (where dq_issues array is not empty)
        # AND ensure only current records (is_current = true) are used for aggregation.
        app_logger.info("Filtering out records with data quality issues (dq_issues column is not empty) and non-current records (is_current = false).")
        
        # Original counts for logging
        original_orders_count = df_orders_processed.count()
        original_customers_count = df_customers_processed.count()
        original_products_count = df_products_processed.count()

        df_orders_clean_current = df_orders_processed.filter(
            (size(col("dq_issues")) == 0) & (col("is_current") == True)
        )
        df_customers_clean_current = df_customers_processed.filter(
            (size(col("dq_issues")) == 0) & (col("is_current") == True)
        )
        df_products_clean_current = df_products_processed.filter(
            (size(col("dq_issues")) == 0) & (col("is_current") == True)
        )

        app_logger.info(f"Orders: {original_orders_count} rows before filters, {df_orders_clean_current.count()} rows after.")
        app_logger.info(f"Customers: {original_customers_count} rows before filters, {df_customers_clean_current.count()} rows after.")
        app_logger.info(f"Products: {original_products_count} rows before filters, {df_products_clean_current.count()} rows after.")

        # Select required columns
        # Note: We select only the business columns needed for aggregation, not SCD Type 2 or DQ columns.
        df_orders_selected = df_orders_clean_current.select("order_date", "profit", "customer_id", "product_id")
        df_customers_selected = df_customers_clean_current.select("customer_id", "customer_name", "country")
        df_products_selected = df_products_clean_current.select("product_id", "category", "sub_category")

        # Repartition DataFrames for optimized joins
        app_logger.info("Repartitioning DataFrames for optimized joins.")
        df_orders_partitioned = df_orders_selected.repartition("customer_id", "product_id")
        df_customers_partitioned = df_customers_selected.repartition("customer_id")
        df_products_partitioned = df_products_selected.repartition("product_id")

        app_logger.info("Finished selection, data quality filtering, SCD Type 2 filtering, and repartitioning of DataFrames.")
        return df_orders_partitioned, df_customers_partitioned, df_products_partitioned
    except Exception as e:
        app_logger.error(f"Failed during selection, data quality filtering, SCD Type 2 filtering, or repartitioning. Reason: {e}")
        raise

def join_ecomm_data(
    df_orders: DataFrame,
    df_customers: DataFrame,
    df_products: DataFrame
) -> DataFrame:
    """
    Performs an inner join on orders, customers, and products dataframes.
    Assumes inputs are already selected/partitioned as needed.
    
    Args:
        df_orders (DataFrame): Orders DataFrame (selected and partitioned).
        df_customers (DataFrame): Customers DataFrame (selected and partitioned).
        df_products (DataFrame): Products DataFrame (selected and partitioned).

    Returns:
        DataFrame: The joined DataFrame containing combined e-commerce data.

    Raises:
        Exception: If any error occurs during the join operation.
    """
    try:
        app_logger.info("Starting join operation for orders, customers, and products data.")
        
        initial_orders_count = df_orders.count()
        initial_customers_count = df_customers.count()
        initial_products_count = df_products.count()
        app_logger.info(f"Rows before join: Orders={initial_orders_count}, Customers={initial_customers_count}, Products={initial_products_count}")

        # Join Orders with Customers
        df_orders_customers_joined = df_orders.join(
            broadcast(df_customers), "customer_id", "inner"
        )
        app_logger.info(f"Rows after Orders-Customers join: {df_orders_customers_joined.count()}")

        # Join the result with Products
        df_combined_data = df_orders_customers_joined.join(
            broadcast(df_products), "product_id", "inner"
        )
        app_logger.info(f"Rows after all joins: {df_combined_data.count()}")

        if df_combined_data.count() == 0:
            app_logger.warning("No records remained after joining. This might indicate data mismatch or issues.")

        app_logger.info("Finished join operation.")
        return df_combined_data
    except Exception as e:
        app_logger.error(f"Failed during join operation. Reason: {e}")
        raise

def aggregate_profit(df_combined_data: DataFrame) -> DataFrame:
    """
    Aggregates profit by year, category, sub_category, and customer_id.
    
    Args:
        df_combined_data (DataFrame): The DataFrame containing combined e-commerce data.

    Returns:
        DataFrame: The aggregated DataFrame with total profit.

    Raises:
        Exception: If any error occurs during the aggregation.
    """
    try:
        app_logger.info("Starting profit aggregation.")
        
        initial_count = df_combined_data.count()
        app_logger.info(f"Rows before aggregation: {initial_count}")

        df_profit_agg = df_combined_data.groupBy(
            year("order_date").alias("order_year"),
            "category",
            "sub_category",
            "customer_id"
        ).agg(
            sum("profit").alias("total_profit")
        ).orderBy(
            "order_year",
            "category",
            "sub_category",
            "customer_id"
        )
        
        app_logger.info(f"Rows after aggregation: {df_profit_agg.count()}")
        app_logger.info("Finished profit aggregation.")
        return df_profit_agg
    except Exception as e:
        app_logger.error(f"Failed during profit aggregation. Reason: {e}")
        raise

def load_aggregated_data(spark, schemaname: str, df: DataFrame, table_name: str) -> DataFrame:
    """
    Loads a DataFrame into a Delta table in the specified schema.
    
    Args:
        spark: The SparkSession object.
        schemaname (str): The name of the schema (e.g., "analytics").
        df (DataFrame): The DataFrame to be saved.
        table_name (str): The name of the table to save to (e.g., "profit_by_customer_product").

    Returns:
        DataFrame: The DataFrame that was saved.

    Raises:
        RuntimeError: If saving data to the Delta table fails.
    """
    try:
        full_table_name = f"{schemaname}.{table_name}"
        app_logger.info(f"Attempting to save aggregated data to table: {full_table_name}")
        # Note: Aggregated tables are often not partitioned by file_date but by a relevant business key
        # For simplicity, we'll use overwrite mode. Consider append/upsert strategies for production.
        df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(full_table_name)
        app_logger.info(f"Successfully saved aggregated data to {full_table_name}")
        return df
    except Exception as e:
        app_logger.error(f"Failed to save aggregated data to table {full_table_name}. Reason: {e}")
        raise RuntimeError(f"Aggregated data saving failed for {full_table_name}: {e}")


def ecomm_aggregation_pipeline(
    spark,
    df_customers_processed: DataFrame,
    df_orders_processed: DataFrame,
    df_products_processed: DataFrame,
    target_schemaname: str = "analytics",
    target_table_name: str = "profit_by_customer_product"
) -> DataFrame:
    """
    Orchestrates the full e-commerce aggregation pipeline:
    1. Selects relevant columns and filters out records with DQ issues and non-current SCD Type 2 records
       from processed tables.
    2. Repartitions DataFrames for optimized joins.
    3. Joins orders, customers, and products data.
    4. Aggregates profit data.
    5. Loads the aggregated data to a target Delta table.

    Args:
        spark: The SparkSession object.
        df_customers_processed (DataFrame): The processed customers DataFrame (from 'processed' schema).
        df_orders_processed (DataFrame): The processed orders DataFrame (from 'processed' schema).
        df_products_processed (DataFrame): The processed products DataFrame (from 'processed' schema).
        target_schemaname (str): The schema name for the aggregated output table.
        target_table_name (str): The table name for the aggregated output.

    Returns:
        DataFrame: The final aggregated DataFrame.

    Raises:
        Exception: If any critical step in the pipeline fails.
    """
    try:
        app_logger.info("Starting e-commerce aggregation pipeline.")

        # Step 1 & 2: Select, filter DQ issues and non-current records, and repartition DataFrames
        df_orders_part, df_customers_part, df_products_part = \
            select_and_repartition_dataframes(df_customers_processed, df_orders_processed, df_products_processed)

        # Step 3: Join the DataFrames
        df_combined_data = join_ecomm_data(df_orders_part, df_customers_part, df_products_part)

        # Step 4: Aggregate Profit
        df_profit_agg = aggregate_profit(df_combined_data)

        # Step 5: Load Aggregated Data
        load_aggregated_data(spark, target_schemaname, df_profit_agg, target_table_name)

        app_logger.info("E-commerce aggregation pipeline completed successfully.")
        return df_profit_agg
    except Exception as e:
        app_logger.critical(f"E-commerce aggregation pipeline failed. Reason: {e}", exc_info=True)
        raise
