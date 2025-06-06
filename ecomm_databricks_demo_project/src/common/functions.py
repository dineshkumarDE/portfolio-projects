import logging
import os
from datetime import datetime
from pyspark.sql.functions import current_timestamp, lit
from pyspark.sql.types import TimestampType # Ensure TimestampType is imported if used directly here

# Initialize the application logger
app_logger = logging.getLogger("EcommIngestionPipeline")
app_logger.setLevel(logging.INFO) # Set the default logging level for the logger

# Create a formatter for log messages
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Global variables to store ADLS path and dbutils instance for post-run copy
_adls_destination_log_path = None
_dbutils_instance_for_copy = None
_local_log_file_path_for_copy = None

# Custom handler to ensure logs are written to a local file immediately
class LocalFileLogHandler(logging.FileHandler):
    def __init__(self, filename, mode='a', encoding=None, delay=False):
        # Ensure the directory exists before opening the file
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        super().__init__(filename, mode, encoding, delay)

def add_ingestion_date(input_df):
    """
    Adds an 'ingestion_timestamp' column to the DataFrame with the current timestamp.
    This function was previously named add_ingestion_date but now creates a timestamp column
    with the new name to align with the processed schema.
    """
    # Renamed the column to 'ingestion_timestamp'
    output_df = input_df.withColumn("ingestion_timestamp", current_timestamp().cast(TimestampType()))
    return output_df

def setup_logging_local(log_base_path: str, file_date: str, file_type: str, dbutils_instance):
    """
    Configures logging to write to both console and a local file on the Databricks driver.
    If the local log file exists from a previous run, it will be deleted to ensure a fresh log.
    Sets up global variables for the final ADLS copy path.

    Args:
        log_base_path (str): The base ADLS path (e.g., "abfss://logs@ecomdemo.dfs.core.windows.net/").
        file_date (str): The date string (e.g., "YYYY-MM-DD").
        file_type (str): A string indicating the type of file/process (e.g., "products").
        dbutils_instance: The dbutils object from the Databricks environment.
    """
    global _adls_destination_log_path, _dbutils_instance_for_copy, _local_log_file_path_for_copy

    # Clear existing handlers to prevent duplicate logs if called multiple times
    # This is crucial when setup_logging_local might be called multiple times in a notebook session
    for handler in app_logger.handlers[:]:
        app_logger.removeHandler(handler)

    # 1. Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    console_handler.setLevel(logging.INFO)
    app_logger.addHandler(console_handler)

    # Determine local and ADLS paths
    log_year = datetime.strptime(file_date, "%Y-%m-%d").year
    # Local path for the log file on the driver node
    local_log_filename = f"{file_type}_ingestion_{file_date}.log"
    # Using /tmp is standard for temporary files on Databricks driver
    local_base_dir = f"/tmp/ecomm_logs/{log_year}/"
    local_log_file_path = os.path.join(local_base_dir, local_log_filename) # Use os.path.join for robustness

    # ADLS path where the log will eventually be copied.
    # The timestamp for ADLS file will be added in copy_local_log_to_adls function.
    adls_destination_log_base_path = f"{log_base_path}{log_year}/"
    adls_destination_log_file_name_prefix = os.path.splitext(local_log_filename)[0] # e.g., "products_ingestion_2025-05-23"

    # Store global variables for the copy function
    _adls_destination_log_path = adls_destination_log_base_path + adls_destination_log_file_name_prefix # Store prefix for timestamp addition
    _dbutils_instance_for_copy = dbutils_instance
    _local_log_file_path_for_copy = local_log_file_path

    # 2. Local File Handler
    try:
        # --- NEW LOGIC: Delete local file if it exists ---
        # Ensure the local directory exists before checking/deleting the file
        os.makedirs(local_base_dir, exist_ok=True)
        
        if os.path.exists(local_log_file_path):
            app_logger.info(f"Existing local log file found at: {local_log_file_path}. Deleting it for a fresh run.")
            os.remove(local_log_file_path)
            app_logger.info("Local log file successfully deleted.")
        else:
            app_logger.info(f"No existing local log file found at {local_log_file_path}. Creating new.")
        # --- END NEW LOGIC ---

        local_file_handler = LocalFileLogHandler(local_log_file_path, mode='w') # Use 'w' mode to ensure new file if not deleted
        local_file_handler.setFormatter(log_formatter)
        local_file_handler.setLevel(logging.INFO)
        app_logger.addHandler(local_file_handler)
        app_logger.info(f"Local logging configured for: {local_log_file_path}")
    except Exception as e:
        app_logger.error(f"Failed to set up local file logging: {e}. Console logging will continue.")

# Function to copy local log file to ADLS after pipeline run
def copy_local_log_to_adls():
    """
    Copies the local log file from the driver node to the specified ADLS path.
    The ADLS file name will include a timestamp to ensure uniqueness and versioning.
    This should be called at the very end of the pipeline run.
    """
    if _dbutils_instance_for_copy and _local_log_file_path_for_copy and _adls_destination_log_path:
        # Generate a timestamp for the ADLS file name
        adls_timestamp = datetime.now().strftime("_%Y%m%d_%H%M%S")
        # Construct the final ADLS destination path with timestamp
        final_adls_destination_log_path = f"{_adls_destination_log_path}{adls_timestamp}.log"

        app_logger.info(f"Attempting to copy local log file '{_local_log_file_path_for_copy}' to ADLS: '{final_adls_destination_log_path}'")
        try:
            # Ensure the destination directory in ADLS exists
            adls_dir = os.path.dirname(final_adls_destination_log_path)
            _dbutils_instance_for_copy.fs.mkdirs(adls_dir)
            
            # Copy the file. dbutils.fs.cp works with local paths (file:/) and ADLS paths (abfss:/)
            # For local source, it needs 'file:/' prefix
            _dbutils_instance_for_copy.fs.cp(f"file:{_local_log_file_path_for_copy}", final_adls_destination_log_path, recurse=True)
            app_logger.info(f"Successfully copied log file to ADLS: {final_adls_destination_log_path}")
        except Exception as e:
            app_logger.error(f"Failed to copy log file to ADLS: {e}", exc_info=True)
    else:
        app_logger.warning("Log copy to ADLS skipped: Global variables for dbutils or paths not set.")
