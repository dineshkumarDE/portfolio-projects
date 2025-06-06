from pyspark.sql import DataFrame
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, DateType, ArrayType, BooleanType, TimestampType
from pyspark.sql.functions import lit, col, to_date, coalesce, when, array_union, array, size, count, md5, concat_ws, current_date, date_sub, current_timestamp
from common.functions import add_ingestion_date # Assuming this function adds 'ingestion_timestamp'
import logging
import os
from datetime import datetime
from delta.tables import DeltaTable # Import DeltaTable for merge operations

# Assume app_logger and log_formatter are defined and configured externally
app_logger = logging.getLogger("EcommIngestionPipeline")

# Define the schema for the products data
products_schema = StructType([
    StructField("Product ID", StringType(), False), # Non-nullable - will be checked for nulls and rejected
    StructField("Category", StringType(), True),
    StructField("Sub-Category", StringType(), True),
    StructField("Product Name", StringType(), True),
    StructField("State", StringType(), True),
    StructField("Price per product", DoubleType(), True)
])

# Schema for the processed products table (including SCD Type 2 attributes)
# This schema will be used when writing to the 'processed' Delta table
processed_products_schema = StructType([
    StructField("product_id", StringType(), False),
    StructField("category", StringType(), True),
    StructField("sub_category", StringType(), True),
    StructField("product_name", StringType(), True),
    StructField("state", StringType(), True),
    StructField("price_per_product", DoubleType(), True),
    StructField("file_date", DateType(), False), # Date of the source file ingestion
    StructField("dq_issues", ArrayType(StringType()), True), # Data Quality issues column
    StructField("ingestion_timestamp", TimestampType(), False), # Added for consistency
    StructField("effective_start_date", DateType(), False), # SCD Type 2 start date
    StructField("effective_end_date", DateType(), True),     # SCD Type 2 end date
    StructField("is_current", BooleanType(), False),        # SCD Type 2 current flag
    StructField("last_updated_timestamp", TimestampType(), True) # Added for consistency
])


def load_raw_products_csv(spark, file_date: str, raw_path: str, schema: StructType) -> DataFrame:
    """
    Loads raw products data from a CSV file based on the specified schema and date.
    
    Args:
        spark: The SparkSession object.
        file_date (str): The date string for the file path (e.g., "2023-01-15").
        raw_path (str): The base path to the raw data directory.
        schema (StructType): The defined schema for the products data.

    Returns:
        DataFrame: A DataFrame containing the raw products data.

    Raises:
        RuntimeError: If the CSV file loading fails.
    """
    file_path = f"{raw_path}/{file_date}/Products.csv"
    try:
        app_logger.info(f"Attempting to load CSV file from: {file_path}")
        df_raw = spark.read \
            .format("csv") \
            .option("header", "true")\
            .schema(schema) \
            .load(file_path)
        app_logger.info(f"Successfully loaded {df_raw.count()} rows from CSV.")
        return df_raw
    except Exception as e:
        app_logger.error(f"Failed to load CSV file from {file_path}. Reason: {e}")
        raise RuntimeError(f"CSV file loading failed: {e}")

def standardize_products_columns(df_products_raw: DataFrame, file_date: str) -> DataFrame:
    """
    Applies column renaming for standardization (converting "Camel Case" to "snake_case")
    and adds the 'file_date' column.
    
    Args:
        df_products_raw (DataFrame): The raw products DataFrame.
        file_date (str): The date string to be added as 'file_date' column.

    Returns:
        DataFrame: The DataFrame with standardized column names and 'file_date'.

    Raises:
        Exception: If column standardization or adding file_date fails.
    """
    try:
        app_logger.info("Applying column standardization and adding file_date.")
        df_products_renamed = df_products_raw.withColumnRenamed("Product ID", "product_id") \
            .withColumnRenamed("Product Name", "product_name") \
            .withColumnRenamed("Price per product", "price_per_product") \
            .withColumnRenamed("Category", "category") \
            .withColumnRenamed("State", "state")\
            .withColumnRenamed("Sub-Category", "sub_category") \
            .withColumn("file_date", to_date(lit(file_date), 'yyyy-MM-dd'))
        return df_products_renamed
    except Exception as e:
        app_logger.error(f"Failed during column standardization or adding file_date. Reason: {e}")
        raise

def handle_product_id_nulls(spark, df: DataFrame, reject_folder_path: str, file_date: str,dbutils_instance) -> DataFrame:
    """
    Checks for null values in the 'product_id' column.
    Records with null 'product_id' are rejected and saved to a reject folder,
    while valid records are returned.
    """
    app_logger.info("Checking for nulls in the 'product_id' column.")

    # Define the condition for rejection: if product_id is null
    reject_condition = col("product_id").isNull()

    df_rejected = df.filter(reject_condition)
    df_valid = df.filter(~reject_condition) # ~ is the NOT operator

    rejected_count = df_rejected.count()
    total_count = df.count()

    if rejected_count > 0:
        reject_output_path = os.path.join(reject_folder_path, file_date, "Products.rej")
        app_logger.warning(f"Found {rejected_count} records with null 'product_id' out of {total_count} total records.")
        app_logger.info(f"Saving rejected records to: {reject_output_path}")

        try:
            # Create the yearly folder if it doesn't exist
            dbutils_instance.fs.mkdirs(reject_output_path)
            # Save rejected records as JSON (or CSV depending on preference)
            df_rejected.write \
                .format("csv") \
                .mode("overwrite") \
                .option("header", "true") \
                .save(reject_output_path)
            app_logger.info(f"Successfully saved {rejected_count} rejected records.")
        except Exception as e:
            app_logger.error(f"Failed to save rejected records to {reject_output_path}. Reason: {e}")
            # Consider raising an exception here if failure to save rejects is critical
    else:
        app_logger.info("No records found with null 'product_id'. All records are valid in this regard.")

    return df_valid # Return only the valid records for further processing

def clean_and_transform_products_data(df_products_transformed: DataFrame) -> DataFrame:
    """
    Applies data cleaning and specific transformations for products data,
    such as filling null string values with 'unknown' and handling 'price_per_product'.
    
    Args:
        df_products_transformed (DataFrame): The DataFrame with standardized columns.

    Returns:
        DataFrame: The cleaned and transformed DataFrame.

    Raises:
        Exception: If data cleaning or transformation fails.
    """
    try:
        app_logger.info("Applying data cleaning and specific transformations for products.")
        
        # Coalesce nullable StringType fields to "unknown"
        # 'product_id' is non-nullable and handled by rejection, so it's not affected here.
        df_cleaned = df_products_transformed \
            .withColumn("category", coalesce(col("category"), lit("unknown"))) \
            .withColumn("sub_category", coalesce(col("sub_category"), lit("unknown"))) \
            .withColumn("product_name", coalesce(col("product_name"), lit("unknown"))) \
            .withColumn("state", coalesce(col("state"), lit("unknown"))) \
            .withColumn("price_per_product", coalesce(col("price_per_product"), lit(0.0))) # Coalesce price_per_product nulls to 0.0

        # Add any other cleaning logic specific to products here
        return df_cleaned
    except Exception as e:
        app_logger.error(f"Failed during data cleaning or transformation. Reason: {e}")
        raise

def perform_product_data_quality_checks(df: DataFrame) -> DataFrame:
    """
    Performs various data quality checks on the product DataFrame and adds a 'dq_issues' column
    (ArrayType(StringType())) listing any issues found for each row.
    
    Args:
        df (DataFrame): The DataFrame to perform data quality checks on.

    Returns:
        DataFrame: The DataFrame with an added 'dq_issues' column.
    """
    app_logger.info("Performing product data quality checks...")

    # Initialize dq_issues column as an empty array for all rows
    df_dq = df.withColumn("dq_issues", array().cast(ArrayType(StringType())))

    # Check 1: Product ID uniqueness within the current batch
    # This check is now performed on records that *already* have non-null product_ids
    product_id_counts = df_dq.groupBy("product_id").agg(count("*").alias("count"))
    duplicate_product_ids_df = product_id_counts.filter(col("count") > 1).select("product_id")
    duplicate_ids_list = [row.product_id for row in duplicate_product_ids_df.collect()]

    if duplicate_ids_list:
        app_logger.warning(f"Found duplicate Product IDs in the current batch: {duplicate_ids_list}")
        df_dq = df_dq.withColumn("dq_issues",
                                 when(col("product_id").isin(duplicate_ids_list),
                                      array_union(col("dq_issues"), array(lit("PRODUCT_ID_DUPLICATE_IN_BATCH"))))
                                 .otherwise(col("dq_issues")))
    else:
        app_logger.info("No duplicate Product IDs found in the current batch.")

    # Check 2: Price per product must be non-negative
    df_dq = df_dq.withColumn("dq_issues",
                             when(col("price_per_product") < 0, array_union(col("dq_issues"), array(lit("PRICE_PER_PRODUCT_NEGATIVE"))))
                             .otherwise(col("dq_issues")))
    app_logger.info("Price per product non-negativity check applied.")

    # Check 3: Product Name not "unknown" (if it's a critical field, even after coalesce)
    df_dq = df_dq.withColumn("dq_issues",
                             when(col("product_name") == "unknown",
                                  array_union(col("dq_issues"), array(lit("PRODUCT_NAME_IS_UNKNOWN"))))
                             .otherwise(col("dq_issues")))
    app_logger.info("Product Name 'unknown' check applied.")

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


def load_products_data(spark, schemaname: str, df: DataFrame, file_date: str) -> DataFrame:
    """
    Loads a DataFrame into a Delta table in the specified schema.
    This function now handles SCD Type 2 logic for the 'processed' schema,
    tracking changes for products.
    
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
    full_table_name = f"{schemaname}.products"
    
    try:
        if schemaname == "processed":
            app_logger.info(f"Applying SCD Type 2 logic for {full_table_name}.")

            # Define the current processing date
            current_processing_date = to_date(lit(file_date), 'yyyy-MM-dd')

            # Prepare the incoming DataFrame with SCD Type 2 attributes and a change hash
            # The hash includes all attributes that trigger a change in the 'current' record,
            # excluding the SCD meta-columns and the primary key (product_id).
            scd_change_hash_columns = [
                "category", "sub_category", "product_name", "state", "price_per_product"
            ]
            df_incoming = df.withColumn("effective_start_date", current_processing_date) \
                             .withColumn("effective_end_date", lit(None).cast(DateType())) \
                             .withColumn("is_current", lit(True).cast(BooleanType())) \
                             .withColumn("last_updated_timestamp", current_timestamp()) \
                             .withColumn("change_hash", md5(concat_ws("||", *[col(c) for c in scd_change_hash_columns])))

            # Check if the Delta table exists using spark.catalog.tableExists
            if not spark.catalog.tableExists(full_table_name):
                app_logger.info(f"Delta table {full_table_name} does not exist. Creating it with initial load.")
                # Initial load: use df_incoming which already has SCD columns and hash
                df_to_write = df_incoming.drop("change_hash")# Drop hash before writing, it's temporary for merge
                
                df_to_write.write.format("delta").mode("overwrite") \
                                 .partitionBy("effective_start_date") \
                                 .saveAsTable(full_table_name)
                app_logger.info(f"Successfully created and loaded initial data to {full_table_name}.")

                try:
                    app_logger.info(f"Optimizing and ZORDERing {full_table_name} by product_id after initial load.")
                    spark.sql(f"OPTIMIZE {full_table_name} ZORDER BY (product_id)")
                    app_logger.info(f"Optimization and ZORDERing completed for {full_table_name}.")
                except Exception as opt_e:
                    app_logger.warning(f"Failed to optimize/ZORDER {full_table_name} after initial load. Reason: {opt_e}")

                return df_to_write
            else:
                app_logger.info(f"Delta table {full_table_name} exists. Performing merge operation for SCD Type 2.")
                
                delta_table = DeltaTable.forName(spark, full_table_name)
                
                # Step 1: Mark old records as not current if changes detected
                app_logger.info("Step 1: Marking old records as not current (is_current=false) if changes detected.")
                delta_table.alias("target") \
                    .merge(
                        df_incoming.alias("source"),
                        "target.product_id = source.product_id AND target.is_current = true" # Match on product_id
                    ) \
                    .whenMatchedUpdate(
                        condition=f"md5(concat_ws('||', " \
                                  f"target.category, target.sub_category, target.product_name, " \
                                  f"target.state, target.price_per_product" \
                                  f")) != source.change_hash",
                        set={
                            "is_current": lit(False),
                            "effective_end_date": date_sub(col("source.effective_start_date"), 1),
                            "last_updated_timestamp": current_timestamp() # Update last_updated_timestamp when closing
                        }
                    ) \
                    .execute()
                app_logger.info("Step 1 (update) completed.")

                # Step 2: Insert new records or new versions of changed records
                app_logger.info("Step 2: Inserting new records or new versions of changed records.")
                delta_table.alias("target") \
                    .merge(
                        df_incoming.alias("source"),
                        f"target.product_id = source.product_id AND " \
                        f"md5(concat_ws('||', " \
                        f"target.category, target.sub_category, target.product_name, " \
                        f"target.state, target.price_per_product" \
                        f")) = source.change_hash AND target.is_current = true"\
                    ) \
                    .whenNotMatchedInsert(
                        values={
                            "product_id": "source.product_id",
                            "category": "source.category",
                            "sub_category": "source.sub_category",
                            "product_name": "source.product_name",
                            "state": "source.state",
                            "price_per_product": "source.price_per_product",
                            "file_date": "source.file_date",
                            "dq_issues": "source.dq_issues",
                            "ingestion_timestamp": "source.ingestion_timestamp", # Ensure this is carried over
                            "effective_start_date": "source.effective_start_date",
                            "effective_end_date": "source.effective_end_date",
                            "is_current": "source.is_current",
                            "last_updated_timestamp": "source.last_updated_timestamp" # Use the timestamp from the incoming DataFrame,
                            
                        }
                    ) \
                    .execute()
                app_logger.info("Step 2 (insert) completed.")
                
                app_logger.info(f"SCD Type 2 merge completed for {full_table_name}.")

                # --- OPTIMIZE and ZORDER after merge ---
                try:
                    app_logger.info(f"Optimizing and ZORDERing {full_table_name} by product_id after merge.")
                    spark.sql(f"OPTIMIZE {full_table_name} ZORDER BY (product_id)")
                    app_logger.info(f"Optimization and ZORDERing completed for {full_table_name}.")
                except Exception as opt_e:
                    app_logger.warning(f"Failed to optimize/ZORDER {full_table_name} after merge. Reason: {opt_e}")

                # Return the current state of the table after merge
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
def ingest_products_pipeline(spark, file_date: str, raw_folder_path: str, reject_folder_path: str,dbutils_instance):
    """
    Orchestrates the full products ingestion pipeline:
    1. Loads raw CSV data.
    2. Standardizes column names.
    3. Handles null 'product_id' records, rejecting invalid records to a specified folder.
    4. Saves valid records to raw Delta table.
    5. Cleans and transforms data.
    6. Performs detailed data quality checks and flags issues.
    7. Adds ingestion date.
    8. Saves to processed Delta table using SCD Type 2 logic.
    
    Args:
        spark: The SparkSession object.
        file_date (str): The date of the file to be ingested (e.g., "2023-01-15").
        raw_folder_path (str): The base path to the raw data.
        reject_folder_path (str): The base path where rejected records will be stored.

    Returns:
        DataFrame: The final processed DataFrame (after SCD Type 2 merge).

    Raises:
        Exception: If any critical step in the pipeline fails.
    """
    try:
        app_logger.info(f"Starting products ingestion pipeline for file date: {file_date}")

        # Step 1: Load Raw Data
        df_raw = load_raw_products_csv(spark, file_date, raw_folder_path, products_schema)

        # Step 2: Standardize Columns
        df_renamed = standardize_products_columns(df_raw, file_date)

        # Step 3: Handle null 'product_id' records
        df_valid_ids = handle_product_id_nulls(spark, df_renamed, reject_folder_path, file_date,dbutils_instance)

        # Step 4: Load valid records to Raw Schema
        load_products_data(spark, "raw", df_valid_ids, file_date) # Pass file_date for raw layer partitioning

        # Step 5: Clean and Transform Data
        df_cleaned = clean_and_transform_products_data(df_valid_ids)

        # Step 6: Perform Detailed Data Quality Checks
        df_quality_checked = perform_product_data_quality_checks(df_cleaned)

        # Step 7: Add Ingestion Date
        df_final_for_processed = add_ingestion_date(df_quality_checked)

        # Step 8: Load to Processed Schema with SCD Type 2 logic
        df_processed_output = load_products_data(spark, "processed", df_final_for_processed, file_date)

        app_logger.info(f"Products ingestion pipeline completed successfully for file date: {file_date}")
        return df_processed_output # Return the DataFrame representing the current state of processed table
    except Exception as e:
        app_logger.critical(f"Products ingestion pipeline failed for file date {file_date}. Reason: {e}", exc_info=True)
        raise