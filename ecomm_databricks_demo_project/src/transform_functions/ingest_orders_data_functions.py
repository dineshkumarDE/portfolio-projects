from pyspark.sql.types import StructType, StructField, StringType, LongType, IntegerType, DoubleType, DateType
from pyspark.sql.functions import lit, col, count, when, coalesce, round, to_date
from common.functions import add_ingestion_date
from pyspark.sql import DataFrame

# Define the schema for the orders data
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

def load_raw_orders_json(spark, file_date: str, raw_path: str, schema: StructType) -> DataFrame:
    """
    Loads raw orders data from a JSON file based on the specified schema and date.
    Handles multiLine JSON and date format.
    """
    file_path = f"{raw_path}/{file_date}/Orders.json"
    try:
        print(f"Attempting to load JSON file from: {file_path}")
        df_raw = spark.read \
            .format("json") \
            .schema(schema) \
            .option("dateFormat", "d/M/yyyy") \
            .option("multiLine", "true") \
            .load(file_path)
        print(f"Successfully loaded {df_raw.count()} rows from JSON.")
        return df_raw
    except Exception as e:
        print(f"ERROR: Failed to load JSON file from {file_path}. Reason: {e}")
        raise RuntimeError(f"JSON file loading failed: {e}")

def standardize_orders_columns(df_orders_raw: DataFrame, file_date: str) -> DataFrame:
    """
    Applies column renaming for standardization and adds the 'file_date' column.
    
    """
    try:
        print("Applying column standardization and adding file_date.")
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
            .withColumn("file_date", to_date(lit(file_date), "yyyy-MM-dd"))
        return df_orders_renamed
    except Exception as e:
        print(f"ERROR: Failed during column standardization or adding file_date. Reason: {e}")
        raise

def clean_and_transform_orders_data(df_orders_transformed: DataFrame) -> DataFrame:
    """
    Applies data cleaning and specific transformations for orders data,
    such as rounding 'profit'. Add other cleaning rules here if needed.
    """
    try:
        print("Applying data cleaning and specific transformations for orders.")
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
        print(f"ERROR: Failed during data cleaning or transformation. Reason: {e}")
        raise

def load_orders_data(spark, schemaname: str, df: DataFrame) -> DataFrame:
    """
    Loads a DataFrame into a Delta table in the specified schema.
    """
    try:
        full_table_name = f"{schemaname}.orders"
        print(f"Attempting to save data to table: {full_table_name}")
        df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(full_table_name)
        print(f"Successfully saved data to {full_table_name}")
        return df
    except Exception as e:
        print(f"ERROR: Failed to save data to table {full_table_name}. Reason: {e}")
        raise RuntimeError(f"Data saving failed for {full_table_name}: {e}")

# The main pipeline orchestrator
def ingest_orders_pipeline(spark, file_date: str, raw_folder_path: str):
    """
    Orchestrates the full orders ingestion pipeline:
    1. Loads raw JSON data.
    2. Standardizes column names.
    3. Saves to raw Delta table.
    4. Cleans and transforms data.
    5. Adds ingestion date.
    6. Saves to processed Delta table.
    """
    try:
        print(f"Starting orders ingestion pipeline for file date: {file_date}")

        # Step 1: Load Raw Data
        df_raw = load_raw_orders_json(spark, file_date, raw_folder_path, orders_schema)

        # Step 2: Standardize Columns
        df_renamed = standardize_orders_columns(df_raw, file_date)

        # Step 3: Load to Raw Schema
        load_orders_data(spark, "raw", df_renamed)

        # Step 4: Clean and Transform Data
        df_cleaned = clean_and_transform_orders_data(df_renamed)

        # Step 5: Add Ingestion Date using the passed common_functions_module
        df_final = add_ingestion_date(df_cleaned)

        # Step 6: Load to Processed Schema
        load_orders_data(spark, "processed", df_final)

        print(f"Orders ingestion pipeline completed successfully for file date: {file_date}")
        return df_final
    except Exception as e:
        print(f"CRITICAL ERROR: Orders ingestion pipeline failed for file date {file_date}. Reason: {e}")
        raise