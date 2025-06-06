from pyspark.sql.types import StructType, StructField, StringType, LongType, IntegerType, DoubleType, DateType, ArrayType, BooleanType, TimestampType
from pyspark.sql.functions import lit, col, count, when, coalesce, round, to_date, array_union, array, size, md5, concat_ws, current_date, date_sub, current_timestamp
from common.functions import add_ingestion_date 

from pyspark.sql import DataFrame
import logging
import os
from datetime import datetime
from delta.tables import DeltaTable 

app_logger = logging.getLogger("EcommIngestionPipeline")


# Define the schema for the orders data (raw layer)
orders_schema = StructType([
    StructField("Row ID", IntegerType(), False),
    StructField("Order ID", StringType(), False), 
    StructField("Order Date", DateType(), True),
    StructField("Ship Date", DateType(), True),
    StructField("Ship Mode", StringType(), True),
    StructField("Customer ID", StringType(), False), 
    StructField("Product ID", StringType(), False),  
    StructField("Quantity", IntegerType(), True),
    StructField("Price", DoubleType(), True),
    StructField("Discount", DoubleType(), True),
    StructField("Profit", DoubleType(), True)
])

# Schema for the processed orders table (no SCD Type 2 attributes needed)
# This schema will be used when writing to the 'processed' Delta table
processed_orders_schema = StructType([ 
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
    StructField("file_date", DateType(), False), 
    StructField("dq_issues", ArrayType(StringType()), True), 
    StructField("ingestion_timestamp", TimestampType(), False) 
])


def load_raw_orders_json(spark, file_date: str, raw_path: str, schema: StructType) -> DataFrame:
    """
    Loads raw orders data from a JSON file based on the specified schema and date.
    Handles multiLine JSON and date format.
    
    Args:
        spark: The SparkSession object.
        file_date (str): The date string for the file path (e.g., "2023-01-15").
        raw_path (str): The base path to the raw data directory.
        schema (StructType): The defined schema for the orders data.

    Returns:
        DataFrame: A DataFrame containing the raw orders data.

    Raises:
        RuntimeError: If the JSON file loading fails.
    """
    file_path = f"{raw_path}/{file_date}/Orders.json"
    try:
        app_logger.info(f"Attempting to load JSON file from: {file_path}")
        df_raw = spark.read \
            .format("json") \
            .schema(schema) \
            .option("dateFormat", "d/M/yyyy") \
            .option("multiLine", "true") \
            .load(file_path)
        app_logger.info(f"Successfully loaded {df_raw.count()} rows from JSON.")
        return df_raw
    except Exception as e:
        app_logger.error(f"Failed to load JSON file from {file_path}. Reason: {e}")
        raise RuntimeError(f"JSON file loading failed: {e}")

def standardize_orders_columns(df_orders_raw: DataFrame, file_date: str) -> DataFrame:
    """
    Applies column renaming for standardization (converting "Camel Case" to "snake_case")
    and adds the 'file_date' column.
    
    Args:
        df_orders_raw (DataFrame): The raw orders DataFrame.
        file_date (str): The date string to be added as 'file_date' column.

    Returns:
        DataFrame: The DataFrame with standardized column names and 'file_date'.

    Raises:
        Exception: If column standardization or adding file_date fails.
    """
    try:
        app_logger.info("Applying column standardization and adding file_date.")
        df_orders_renamed = df_orders_raw.withColumnRenamed("Row ID", "row_id") \
            .withColumnRenamed("Order ID", "order_id") \
            .withColumnRenamed("Order Date", "order_date") \
            .withColumnRenamed("Ship Date", "ship_date") \
            .withColumnRenamed("Ship Mode", "ship_mode") \
            .withColumnRenamed("Customer ID", "customer_id") \
            .withColumnRenamed("Product ID", "product_id") \
            .withColumnRenamed("Price", "price") \
            .withColumnRenamed("Quantity", "quantity") \
            .withColumnRenamed("Discount", "discount") \
            .withColumnRenamed("Profit", "profit") \
            .withColumn("file_date", to_date(lit(file_date), 'yyyy-MM-dd'))
        return df_orders_renamed
    except Exception as e:
        app_logger.error(f"Failed during column standardization or adding file_date. Reason: {e}")
        raise

def handle_critical_id_nulls(spark, df: DataFrame, reject_folder_path: str, file_date: str,dbutils_instance) -> DataFrame:
    """
    Checks for null values in critical ID columns (order_id, customer_id, product_id, row_id).
    Records with nulls in any of these are rejected and saved to a reject folder,
    while valid records are returned.
    """
    app_logger.info("Checking for nulls in critical ID columns (order_id, customer_id, product_id, row_id).")

    # Define the condition for rejection: if any of these critical IDs are null
    reject_condition = (col("row_id").isNull()) | \
                       (col("order_id").isNull()) | \
                       (col("customer_id").isNull()) | \
                       (col("product_id").isNull())

    df_rejected = df.filter(reject_condition)
    df_valid = df.filter(~reject_condition) 

    rejected_count = df_rejected.count()
    total_count = df.count()

    if rejected_count > 0:
        reject_output_path = os.path.join(reject_folder_path, file_date, "Orders.rej")
        app_logger.warning(f"Found {rejected_count} records with null critical IDs out of {total_count} total records.")
        app_logger.info(f"Saving rejected records to: {reject_output_path}")

        try:
            dbutils_instance.fs.mkdirs(reject_output_path)
            
            df_rejected.write \
                .format("csv") \
                .mode("overwrite") \
                .option("header", "true") \
                .save(reject_output_path)
            app_logger.info(f"Successfully saved {rejected_count} rejected records.")
        except Exception as e:
            app_logger.error(f"Failed to save rejected records to {reject_output_path}. Reason: {e}")
    else:
        app_logger.info("No records found with null critical IDs. All records are valid in this regard.")

    return df_valid 

def clean_and_transform_orders_data(df_orders_transformed: DataFrame) -> DataFrame:
    """
    Applies data cleaning and specific transformations for orders data,
    such as rounding 'profit' and coalescing null values to defaulted values.
    
    NOTE: 'customer_id', 'product_id', and 'row_id' are NOT coalesced here as records
    with nulls in these critical fields are now rejected upstream by handle_critical_id_nulls.
    """
    try:
        app_logger.info("Applying data cleaning and specific transformations for orders.")
        df_cleaned = df_orders_transformed \
            .withColumn("order_date", coalesce(col("order_date"), lit("1900-01-01").cast(DateType()))) \
            .withColumn("ship_date", coalesce(col("ship_date"), lit("1900-01-01").cast(DateType()))) \
            .withColumn("ship_mode", coalesce(col("ship_mode"), lit("unknown"))) \
            .withColumn("quantity", coalesce(col("quantity"), lit(0))) \
            .withColumn("price", coalesce(col("price"), lit(0.0))) \
            .withColumn("discount", coalesce(col("discount"), lit(0.0))) \
            .withColumn("profit", round(coalesce(col("profit"), lit(0.0)), 2))
        return df_cleaned
    except Exception as e:
        app_logger.error(f"Failed during data cleaning or transformation. Reason: {e}")
        raise

def perform_order_data_quality_checks(df: DataFrame) -> DataFrame:
    """
    Performs various data quality checks on the order DataFrame and adds a 'dq_issues' column
    (ArrayType(StringType())) listing any issues found for each row.
    
    Args:
        df (DataFrame): The DataFrame to perform data quality checks on.

    Returns:
        DataFrame: The DataFrame with an added 'dq_issues' column.
    """
    app_logger.info("Performing order data quality checks...")

    # Initialize dq_issues column as an empty array for all rows
    df_dq = df.withColumn("dq_issues", array().cast(ArrayType(StringType())))

    # Check 1: Quantity must be non-negative
    df_dq = df_dq.withColumn("dq_issues",
                             when(col("quantity") < 0, array_union(col("dq_issues"), array(lit("QUANTITY_NEGATIVE"))))
                             .otherwise(col("dq_issues")))
    app_logger.info("Quantity non-negativity check applied.")

    # Check 2: Price must be non-negative
    df_dq = df_dq.withColumn("dq_issues",
                             when(col("price") < 0, array_union(col("dq_issues"), array(lit("PRICE_NEGATIVE"))))
                             .otherwise(col("dq_issues")))
    app_logger.info("Price non-negativity check applied.")

    # Check 3: Discount must be between 0.0 and 1.0 (inclusive)
    df_dq = df_dq.withColumn("dq_issues",
                             when((col("discount") < 0.0) | (col("discount") > 1.0),
                                  array_union(col("dq_issues"), array(lit("DISCOUNT_OUT_OF_RANGE"))))
                             .otherwise(col("dq_issues")))
    app_logger.info("Discount range check applied.")

    # Check 4: Ship Date must be on or after Order Date
    df_dq = df_dq.withColumn("dq_issues",
                             when(col("ship_date") < col("order_date"),
                                  array_union(col("dq_issues"), array(lit("SHIP_DATE_BEFORE_ORDER_DATE"))))
                             .otherwise(col("dq_issues")))
    app_logger.info("Ship Date vs Order Date consistency check applied.")

    # Check 5: Row ID uniqueness within the current batch
    # Since row_id is the unique column, check for its uniqueness in the incoming batch
    row_id_counts = df_dq.groupBy("row_id").agg(count("*").alias("count"))
    duplicate_row_ids_df = row_id_counts.filter(col("count") > 1).select("row_id")
    duplicate_ids_list = [row.row_id for row in duplicate_row_ids_df.collect()]

    if duplicate_ids_list:
        app_logger.warning(f"Found duplicate Row IDs in the current batch: {duplicate_ids_list}")
        df_dq = df_dq.withColumn("dq_issues",
                                 when(col("row_id").isin(duplicate_ids_list),
                                      array_union(col("dq_issues"), array(lit("ROW_ID_DUPLICATE_IN_BATCH"))))
                                 .otherwise(col("dq_issues")))
    else:
        app_logger.info("No duplicate Row IDs found in the current batch.")

    # Log summary of data quality issues
    dq_summary = df_dq.withColumn("has_issues", size(col("dq_issues")) > 0) \
                      .groupBy("has_issues") \
                      .count() \
                      .collect()

    total_rows = df_dq.count()
    issues_count = 0
    for row in dq_summary:
        if row.has_issues:
            issues_count = row["count"]
            app_logger.info(f"SUMMARY: {issues_count} out of {total_rows} rows have data quality issues.")
        else:
            app_logger.info(f"SUMMARY: {row['count']} rows passed all data quality checks.")

    if issues_count > 0:
        app_logger.info("Consider reviewing rows with 'dq_issues' column for details on specific issues.")

    return df_dq

def load_orders_data(spark, schemaname: str, df: DataFrame, file_date: str) -> DataFrame:
    """
    Loads a DataFrame into a Delta table in the specified schema.
    For 'processed' schema, data is appended daily.
    
    Args:
        spark: The SparkSession object.
        schemaname (str): The name of the schema (e.g., "raw", "processed").
        df (DataFrame): The DataFrame to be saved.
        file_date (str): The date of the file being processed, used as the effective date.

    Returns:
        DataFrame: The DataFrame that was saved.

    Raises:
        RuntimeError: If saving data to the Delta table fails.
    """
    full_table_name = f"{schemaname}.orders"
    
    try:
        if schemaname == "processed":
            app_logger.info(f"Loading data to {full_table_name} with 'append' mode, partitioned by file_date.")

            # No SCD Type 2 specific columns needed here, as we are simply appending
            # The 'file_date' and 'ingestion_timestamp' are already present in df_final_for_processed
            
            # Check if the Delta table exists using spark.catalog.tableExists
            if not spark.catalog.tableExists(full_table_name):
                app_logger.info(f"Delta table {full_table_name} does not exist. Creating it with initial load.")
                # For initial load, use overwrite and define partitions.
                # Ensure the schema includes 'file_date' and 'ingestion_timestamp'
                df.write.format("delta").mode("overwrite") \
                                 .option("overwriteSchema", "true") \
                                 .partitionBy("file_date") \
                                 .saveAsTable(full_table_name)
                app_logger.info(f"Successfully created and loaded initial data to {full_table_name}.")
            else:
                app_logger.info(f"Delta table {full_table_name} exists. Appending new data.")
                # For subsequent loads, append data to the existing table.
                # Spark will automatically place the new data into the correct file_date partitions.
                df.write.format("delta").mode("append").saveAsTable(full_table_name)
                app_logger.info(f"Successfully appended data to {full_table_name}.")

            # Optimize and ZORDER after each load for better performance, especially with daily appends.
            try:
                app_logger.info(f"Optimizing and ZORDERing {full_table_name} by order_id, row_id after load.")
                spark.sql(f"OPTIMIZE {full_table_name} ZORDER BY (order_id, row_id)")
                app_logger.info(f"Optimization and ZORDERing completed for {full_table_name}.")
            except Exception as opt_e:
                app_logger.warning(f"Failed to optimize/ZORDER {full_table_name} after load. Reason: {opt_e}")

            return spark.read.format("delta").table(full_table_name)

        else: # For 'raw' schema
            app_logger.info(f"Attempting to save data to table: {full_table_name} with 'overwrite' mode and partitioning by file_date.")
            df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").partitionBy("file_date").saveAsTable(full_table_name)
            app_logger.info(f"Successfully saved data to {full_table_name}")
            return df
            
    except Exception as e:
        app_logger.error(f"Failed to save data to table {full_table_name}. Reason: {e}")
        raise RuntimeError(f"Data saving failed for {full_table_name}: {e}")

# The main pipeline orchestrator
def ingest_orders_pipeline(spark, file_date: str, raw_folder_path: str, reject_folder_path: str,dbutils_instance):
    """
    Orchestrates the full orders ingestion pipeline:
    1. Loads raw JSON data.
    2. Standardizes column names.
    3. Handles null critical IDs (order_id, customer_id, product_id, row_id), rejecting invalid records.
    4. Saves valid records to raw Delta table.
    5. Cleans and transforms data.
    6. Performs detailed data quality checks and flags issues.
    7. Adds ingestion date.
    8. Saves to processed Delta table using append logic.
    
    Args:
        spark: The SparkSession object.
        file_date (str): The date of the file to be ingested (e.g., "YYYY-MM-DD").
        raw_folder_path (str): The base path to the raw data.
        reject_folder_path (str): The base path where rejected records will be stored.

    Returns:
        DataFrame: The final processed DataFrame.

    Raises:
        Exception: If any critical step in the pipeline fails.
    """
    try:
        app_logger.info(f"Starting orders ingestion pipeline for file date: {file_date}")

        # Step 1: Load Raw Data
        df_raw = load_raw_orders_json(spark, file_date, raw_folder_path, orders_schema)

        # Step 2: Standardize Columns
        df_renamed = standardize_orders_columns(df_raw, file_date)

        # Step 3: Handle null critical IDs (order_id, customer_id, product_id, row_id)
        df_valid_ids = handle_critical_id_nulls(spark, df_renamed, reject_folder_path, file_date,dbutils_instance)

        # Step 4: Load valid records to Raw Schema
        load_orders_data(spark, "raw", df_valid_ids, file_date)

        # Step 5: Clean and Transform Data
        df_cleaned = clean_and_transform_orders_data(df_valid_ids)

        # Step 6: Perform Detailed Data Quality Checks
        df_quality_checked = perform_order_data_quality_checks(df_cleaned)

        # Step 7: Add Ingestion Date
        # Ensure common.functions.add_ingestion_date adds 'ingestion_timestamp' as it will be needed
        df_final_for_processed = add_ingestion_date(df_quality_checked)

        # Step 8: Load to Processed Schema with Append logic (no SCD Type 2)
        df_processed_output = load_orders_data(spark, "processed", df_final_for_processed, file_date)

        app_logger.info(f"Orders ingestion pipeline completed successfully for file date: {file_date}")
        return df_processed_output
    except Exception as e:
        app_logger.critical(f"Orders ingestion pipeline failed for file date {file_date}. Reason: {e}", exc_info=True)
        raise