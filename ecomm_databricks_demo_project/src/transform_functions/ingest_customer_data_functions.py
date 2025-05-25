# Databricks notebook source

from pyspark.sql.types import StructType, StructField, StringType, DateType
from pyspark.sql.functions import lit, col, coalesce, when, to_date
from common.functions import add_ingestion_date


customer_schema = StructType([
    StructField("Customer ID", StringType(), False),
    StructField("Customer Name", StringType(), True),
    StructField("email", StringType(), True),
    StructField("phone", StringType(), True),
    StructField("address", StringType(), True),
    StructField("Segment", StringType(), True),
    StructField("Country", StringType(), True),
    StructField("City", StringType(), True),
    StructField("State", StringType(), True),
    StructField("Postal Code", StringType(), True),
    StructField("Region", StringType(), True)
])

def load_raw_customer_excel(spark, file_date: str, raw_path: str, schema: StructType):
    """
    Loads raw customer data from an Excel file.
    """
    file_path = f"{raw_path}/{file_date}/Customer.xlsx"
    try:
        print(f"Attempting to load Excel file from: {file_path}")
        df_raw = spark.read \
            .format("com.crealytics.spark.excel") \
            .option("header", "true") \
            .schema(schema) \
            .option("sheetName", "Worksheet") \
            .load(file_path)
        print(f"Successfully loaded {df_raw.count()} rows from Excel.")
        return df_raw
    except Exception as e:
        # This is critical for external file loading errors (file not found, corrupt, permission issues)
        print(f"ERROR: Failed to load Excel file from {file_path}. Reason: {e}")
        raise RuntimeError(f"Excel file loading failed: {e}") # Re-raise as a more specific error

def customer_column_standardize(df_customer_raw, file_date: str):
    """
    Applies renaming and adds file_date column.
    """
    try:
        print("Applying column standardization and adding file_date.")
        df_customer_renamed = df_customer_raw.withColumnRenamed("Customer ID", "customer_id") \
            .withColumnRenamed("Customer Name", "customer_name") \
            .withColumnRenamed("Segment", "segment") \
            .withColumnRenamed("Country", "country") \
            .withColumnRenamed("City", "city") \
            .withColumnRenamed("State", "state") \
            .withColumnRenamed("Postal Code", "postal_code") \
            .withColumnRenamed("Region", "region") \
            .withColumn("file_date", to_date(lit(file_date), 'yyyy-MM-dd'))
        return df_customer_renamed
    except Exception as e:
        print(f"ERROR: Failed during column standardization or adding file_date. Reason: {e}")
        raise # Re-raise to indicate transformation failure

def clean_customer_data(df_customer_transformed):
    """
    Applies data cleaning logic for customer_name and phone.
    """
    try:
        print("Applying data cleaning for customer_name and phone.")
        df_customer_cleaned = df_customer_transformed.withColumn(
            "customer_name",
            coalesce(col("customer_name"), lit("unknown"))
        ).withColumn(
            "phone",
            when(col("phone") == "#ERROR!", "unknown").otherwise(col("phone"))
        )
        return df_customer_cleaned
    except Exception as e:
        print(f"ERROR: Failed during data cleaning. Reason: {e}")
        raise # Re-raise to indicate transformation failure

def load_customer_data(spark, schemaname: str, df):
    """
    Loads data into raw & processed schema.
    """
    try:
        full_table_name = f"{schemaname}.customers"
        print(f"Attempting to save data to table: {full_table_name}")
        df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(full_table_name)
        print(f"Successfully saved data to {full_table_name}")
        return df
    except Exception as e:
        # This is critical for saving operations (permissions, Delta Lake issues, disk space)
        print(f"ERROR: Failed to save data to table {full_table_name}. Reason: {e}")
        raise RuntimeError(f"Data saving failed for {full_table_name}: {e}") # Re-raise as a specific error

def ingest_customer_pipeline(spark, file_date: str, raw_path: str):
    """
    Orchestrates the full ingestion pipeline.
    """
    try:
        print(f"Starting customer ingestion pipeline for file date: {file_date}")

        # Step 1: Load Raw Data
        df_raw = load_raw_customer_excel(spark, file_date, raw_path, customer_schema)
        # If load_raw_customer_excel fails, it will raise an exception which is caught by the outer try-except

        # Step 2: Standardize Columns
        df_renamed = customer_column_standardize(df_raw, file_date)

        # Step 3: Load to Raw Schema (if this is a separate staging step before final processing)

        df_raw_final = load_customer_data(spark, "raw", df_renamed) # df_raw_final will be the df returned by load_customer_data

        # Step 4: Clean Data
        df_cleaned = clean_customer_data(df_raw_final)

        # Step 5: Add Ingestion Date
        df_final = add_ingestion_date(df_cleaned)

        # Step 6: Load to Processed Schema
        load_customer_data(spark, "processed", df_final)

        print(f"Customer ingestion pipeline completed successfully for file date: {file_date}")
        return df_final # Return the final DataFrame for potential inspection/chaining
    except Exception as e:
        print(f"CRITICAL ERROR: Customer ingestion pipeline failed for file date {file_date}. Reason: {e}")
        raise # Re-raise the exception to signal pipeline failure