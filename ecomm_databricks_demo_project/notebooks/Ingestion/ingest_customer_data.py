# Databricks notebook source
# MAGIC %md
# MAGIC ###Ingesting Customer data
# MAGIC

# COMMAND ----------

# Define widgets
dbutils.widgets.text("p_file_date", "2025-05-23")
v_file_date = dbutils.widgets.get("p_file_date")

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
from transform_functions.ingest_customer_data_functions import *

# COMMAND ----------

# %run "../includes/configuration"


# COMMAND ----------

# %run "../includes/common_functions"

# COMMAND ----------

# %run "./ingest_customer_data_functions"

# COMMAND ----------

print(raw_folder_path)

# COMMAND ----------

ingest_customer_pipeline(spark, v_file_date, raw_folder_path)
