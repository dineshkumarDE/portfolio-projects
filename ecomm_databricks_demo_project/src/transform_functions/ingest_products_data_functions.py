# src/data_transforms/products_ingestion.py

from pyspark.sql import DataFrame
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, DateType
from pyspark.sql.functions import lit, col, to_date
from common.functions import add_ingestion_date

# Define the schema for the products data
products_schema = StructType([
    StructField("Product ID", StringType(), False),
    StructField("Category", StringType(), True),
    StructField("Sub-Category", StringType(), True),
    StructField("Product Name", StringType(), True),
    StructField("State", StringType(), True),
    StructField("Price per product", DoubleType(), True)
])

def load_raw_products_csv(spark, file_date: str, raw_path: str, schema: StructType) -> DataFrame:
    """
    Loads raw products data from a CSV file based on the specified schema and date.
    """
    file_path = f"{raw_path}/{file_date}/Products.csv"
    try:
        print(f"Attempting to load CSV file from: {file_path}")
        df_raw = spark.read \
            .format("csv") \
            .option("header", "true")\
            .schema(schema) \
            .load(file_path)
        print(f"Successfully loaded {df_raw.count()} rows from CSV.")
        return df_raw
    except Exception as e:
        print(f"ERROR: Failed to load CSV file from {file_path}. Reason: {e}")
        raise RuntimeError(f"CSV file loading failed: {e}")

def standardize_products_columns(df_products_raw: DataFrame, file_date: str) -> DataFrame:
    """
    Applies column renaming for standardization and adds the 'file_date' column.
    """
    try:
        print("Applying column standardization and adding file_date.")
        df_products_renamed = df_products_raw.withColumnRenamed("Product ID", "product_id") \
            .withColumnRenamed("Product Name", "product_name") \
            .withColumnRenamed("Price per product", "price_per_product") \
            .withColumnRenamed("Category", "category") \
            .withColumnRenamed("State", "state")\
            .withColumnRenamed("Sub-Category", "sub_category") \
            .withColumn("file_date", to_date(lit(file_date), 'yyyy-MM-dd'))
        return df_products_renamed
    except Exception as e:
        print(f"ERROR: Failed during column standardization or adding file_date. Reason: {e}")
        raise

def clean_and_transform_products_data(df_products_transformed: DataFrame) -> DataFrame:
    """
    Applies data cleaning and specific transformations for products data,
    such as filling null 'price_per_product' with 0.
    """
    try:
        print("Applying data cleaning and specific transformations for products.")
        # Fill null 'price_per_product' with 0
        df_cleaned = df_products_transformed.fillna({'price_per_product': 0},{'category': 'unknown', 'sub_category': 'unknown', 'product_name': 'unknown', 'state': 'unknown'})
        # Add any other cleaning logic specific to products here
        return df_cleaned
    except Exception as e:
        print(f"ERROR: Failed during data cleaning or transformation. Reason: {e}")
        raise

def load_products_data(spark, schemaname: str, df: DataFrame) -> DataFrame:
    """
    Loads a DataFrame into a Delta table in the specified schema.
    """
    try:
        full_table_name = f"{schemaname}.products"
        print(f"Attempting to save data to table: {full_table_name}")
        df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").partitionBy("file_date").saveAsTable(full_table_name)
        print(f"Successfully saved data to {full_table_name}")
        return df
    except Exception as e:
        print(f"ERROR: Failed to save data to table {full_table_name}. Reason: {e}")
        raise RuntimeError(f"Data saving failed for {full_table_name}: {e}")

# The main pipeline orchestrator
def ingest_products_pipeline(spark, file_date: str, raw_folder_path: str):
    """
    Orchestrates the full products ingestion pipeline:
    1. Loads raw CSV data.
    2. Standardizes column names.
    3. Saves to raw Delta table.
    4. Cleans and transforms data.
    5. Adds ingestion date.
    6. Saves to processed Delta table.
    """
    try:
        print(f"Starting products ingestion pipeline for file date: {file_date}")

        # Step 1: Load Raw Data
        df_raw = load_raw_products_csv(spark, file_date, raw_folder_path, products_schema)

        # Step 2: Standardize Columns
        df_renamed = standardize_products_columns(df_raw, file_date)

        # Step 3: Load to Raw Schema
        load_products_data(spark, "raw", df_renamed)

        # Step 4: Clean and Transform Data
        df_cleaned = clean_and_transform_products_data(df_renamed)

        # Step 5: Add Ingestion Date using the passed common_functions_module
        df_final = add_ingestion_date(df_cleaned)

        # Step 6: Load to Processed Schema
        load_products_data(spark, "processed", df_final)

        print(f"Products ingestion pipeline completed successfully for file date: {file_date}")
        return df_final
    except Exception as e:
        print(f"CRITICAL ERROR: Products ingestion pipeline failed for file date {file_date}. Reason: {e}")
        raise