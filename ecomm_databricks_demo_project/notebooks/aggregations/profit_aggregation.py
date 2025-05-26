# Databricks notebook source
# imports
from pyspark.sql.functions import year,sum
from delta.tables import DeltaTable
from pyspark.sql.functions import col,broadcast
import sys
import os
src_path = os.path.abspath('../../src')
if src_path not in sys.path:
    sys.path.append(src_path)
sys.path
# Import your new functions
from transform_functions.aggregation_functions import (
    select_and_repartition_dataframes,
    join_ecomm_data,
    aggregate_profit
)

# COMMAND ----------

# Optimize tables (these are infrastructure steps, keep them here)
DeltaTable.forName(spark, "processed.orders").optimize().executeZOrderBy("customer_id", "order_date")
DeltaTable.forName(spark, "processed.customers").optimize().executeZOrderBy("customer_id")
DeltaTable.forName(spark, "processed.products").optimize().executeZOrderBy("product_id", "category", "sub_category")

# COMMAND ----------

# Read the processed data
df_customers_processed_raw = spark.read.format("delta").table("processed.customers")
df_orders_processed_raw = spark.read.format("delta").table("processed.orders")
df_products_processed_raw = spark.read.format("delta").table("processed.products")

# COMMAND ----------

# Use the new function to select and repartition
df_orders_partitioned, df_customers_partitioned, df_products_partitioned = \
    select_and_repartition_dataframes(
        df_customers_processed_raw,
        df_orders_processed_raw,
        df_products_processed_raw
    )

# COMMAND ----------

# Use the new function to join data
df_orders_customers_products_joined = join_ecomm_data(
    df_orders_partitioned,
    df_customers_partitioned,
    df_products_partitioned
)

#display(df_orders_customers_products_joined)

# COMMAND ----------

# Load combined data into processed layer
df_orders_customers_products_joined.write.mode("overwrite").format("delta").option("overwriteschema",True).saveAsTable("processed.ecomm_combined_data")

# COMMAND ----------

# Optimize the combined_data table with Z-ordering
print("Optimizing combined_data table with Z-ordering...")
DeltaTable.forName(spark, "processed.ecomm_combined_data").optimize().executeZOrderBy("customer_id", "order_date", "category", "sub_category")
print("Combined data table loaded and optimized successfully.")

# COMMAND ----------

# Read the combined data (if needed for further processing or if aggregate_profit is the next step in the pipeline)
df_combined_data_for_agg = spark.read.format("delta").table("processed.ecomm_combined_data")

# Aggregate profit using the new function
df_profit_agg = aggregate_profit(df_combined_data_for_agg)

df_profit_agg.write.mode("overwrite").format("delta").saveAsTable("presentation.ecomm_profit_agg")

# COMMAND ----------

DeltaTable.forName(spark, "presentation.ecomm_profit_agg").optimize().executeZOrderBy("customer_id", "order_year", "category", "sub_category")

# COMMAND ----------

display(df_profit_agg)
