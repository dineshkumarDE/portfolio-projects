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
from common.functions import *

# COMMAND ----------

# Load combined data into processed layer
permanent_view_name = "processed.ecomm_combined_data_view_permanent" # Use a qualified name (database.view_name)

try:
    app_logger.info(f"Attempting to create or replace permanent view: {permanent_view_name}")

    # This SQL query should represent the logic of how df_orders_customers_products_joined was built
    # You'll need to adapt this SQL to match your actual joining and filtering logic.
    # IMPORTANT: Ensure 'is_current = true' and 'size(dq_issues) = 0' are included
    # if you want the view to always show current and clean data from your processed tables.
    create_view_sql = f"""
        CREATE OR REPLACE VIEW {permanent_view_name}
        AS
        SELECT
            o.order_date,
            o.profit,
            o.customer_id,
            o.product_id,
            c.customer_name,
            c.country,
            p.category,
            p.sub_category
        FROM
            processed.orders o
        INNER JOIN
            processed.customers c ON o.customer_id = c.customer_id
        INNER JOIN
            processed.products p ON o.product_id = p.product_id
        WHERE
            size(o.dq_issues) = 0
            AND c.is_current = TRUE AND size(c.dq_issues) = 0
            AND p.is_current = TRUE AND size(p.dq_issues) = 0
    """
    spark.sql(create_view_sql)
    app_logger.info(f"Successfully created or replaced permanent view: {permanent_view_name}")

    # Now anyone in any SparkSession can query it using SQL:
    print(f"\n--- Querying Permanent View: {permanent_view_name} ---")
    spark.sql(f"SELECT * FROM {permanent_view_name} LIMIT 10").show()

except Exception as e:
    app_logger.error(f"Failed to create permanent view '{permanent_view_name}'. Reason: {e}")
    raise RuntimeError(f"Permanent view creation failed: {e}")

# COMMAND ----------

# Read the combined data (if needed for further processing or if aggregate_profit is the next step in the pipeline)
df_combined_data_for_agg =  spark.table(permanent_view_name)

# Aggregate profit using the new function
df_profit_agg = aggregate_profit(df_combined_data_for_agg)
partition_cols = ["order_year", "category", "sub_category"]
df_profit_agg.write.mode("overwrite").format("delta").partitionBy(*partition_cols).option("overwriteSchema", "true").saveAsTable("presentation.ecomm_profit_agg")

# COMMAND ----------

DeltaTable.forName(spark, "presentation.ecomm_profit_agg").optimize().executeZOrderBy("customer_id")

# COMMAND ----------

display(df_profit_agg)
