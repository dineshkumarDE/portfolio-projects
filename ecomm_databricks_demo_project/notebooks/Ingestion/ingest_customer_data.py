# Databricks notebook source
# MAGIC %md
# MAGIC ###Ingesting Customer data
# MAGIC

# COMMAND ----------

# Define widgets
spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")
dbutils.widgets.text("p_file_date", "2025-05-24")
v_file_date = dbutils.widgets.get("p_file_date")

# COMMAND ----------

import sys
import os
src_path = os.path.abspath('../../src')
if src_path not in sys.path:
    sys.path.append(src_path)
sys.path

# COMMAND ----------

print(v_file_date)

# COMMAND ----------

import importlib
from transform_functions.ingest_customer_data_functions import *
module = importlib.import_module("transform_functions.ingest_customer_data_functions")
importlib.reload(module)
module = importlib.import_module("common.functions")
importlib.reload(module)

# COMMAND ----------

from common.functions import *
from common.configurations import *
from transform_functions.ingest_customer_data_functions import *

# COMMAND ----------

file_type="customers"
_adls_logging_configured = False # Set this to True if setup_logging_local succeeds
try:
    try:
        # Attempt to set up logging to local disk (which eventually copies to ADLS)
        setup_logging_local(log_folder_path, v_file_date, file_type, dbutils)
        _adls_logging_configured = True # Mark as successful
        app_logger.info(f"**Pipeline Execution of {file_type} Started for Date: {v_file_date}**")
    except Exception as e:
        # This catches errors only during the setup_logging_local call
        # Logs to console because ADLS handler might not be working
        print(f"CRITICAL ERROR: Failed to set up ADLS file logging. Logs will only appear in console/driver logs. Reason: {e}")
        # The app_logger will still have the console handler (set up implicitly by setup_logging_local
        # or if setup_logging_local explicitly configures it first).
        app_logger.error(f"Failed to set up ADLS file logging. Reason: {e}. All logs will be console-only.")
        _adls_logging_configured = False # Ensure flag is false

    # --- Main pipeline execution starts here ---
    # This block will run regardless of whether ADLS logging was successfully set up
    ingest_customer_pipeline(spark, v_file_date, raw_folder_path, reject_folder_path,dbutils)

    app_logger.info(f"**Pipeline Execution of {file_type} Completed Successfully for Date: {v_file_date}**")

except Exception as e:
    # This catches exceptions from the main pipeline execution block
    app_logger.exception(f"CRITICAL ERROR: Pipeline execution of {file_type} failed for Date: {v_file_date}. Reason: {e}")
    raise # Re-raise to fail the job if needed

finally:
    # This block ALWAYS executes
    if _adls_logging_configured:
        app_logger.info("Attempting to copy local logs to ADLS...")
        copy_local_log_to_adls() # Attempt the copy if setup was successful
        app_logger.info("Log copy operation finished.")
    else:
        # If ADLS logging wasn't configured, print a console message
        # because app_logger might not have an ADLS handler, or the path might be null
        print("WARNING: ADLS logging was not configured. Skipping attempt to copy logs to ADLS.")
        # We could still call copy_logs_to_adls, but it would just print its own warning
        # as the global path variables would be None. Explicit check here is cleaner.
 
