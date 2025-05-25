# Databricks notebook source
# MAGIC %md
# MAGIC ### Ingesting Orders Data Pipeline Execution
# MAGIC
# MAGIC This notebook orchestrates the ingestion of orders data by calling modular functions.

# COMMAND ----------

# Setup and Configuration
dbutils.widgets.text("p_file_date", "2025-05-23", "File Date (YYYY-MM-DD)")
v_file_date = dbutils.widgets.get("p_file_date")

print(f"Processing orders data for file date: {v_file_date}")

# COMMAND ----------

# %run "../includes/configuration"
# %run "../includes/common_functions" 

# COMMAND ----------

import sys
import os
src_path = os.path.abspath('../../src')
if src_path not in sys.path:
    sys.path.append(src_path)
sys.path

# COMMAND ----------

from common.functions import add_ingestion_date
from common.configurations import raw_folder_path
from transform_functions.ingest_orders_data_functions import *

# COMMAND ----------

# Execute the Orders Ingestion Pipeline
ingest_orders_pipeline(
        spark=spark,
        file_date=v_file_date,
        raw_folder_path=raw_folder_path )
