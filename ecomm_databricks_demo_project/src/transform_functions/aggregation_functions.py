

from pyspark.sql import DataFrame
from pyspark.sql.functions import year, sum, col, broadcast

def select_and_repartition_dataframes(
    df_customers_raw: DataFrame,
    df_orders_raw: DataFrame,
    df_products_raw: DataFrame
) -> (DataFrame, DataFrame, DataFrame):
    """
    Selects required columns and repartitions dataframes.
    Assumes input DataFrames are the 'processed' layer DataFrames.
    """
    df_orders_selected = df_orders_raw.select("order_date", "profit", "customer_id", "product_id")
    df_customers_selected = df_customers_raw.select("customer_id", "customer_name", "country")
    df_products_selected = df_products_raw.select("product_id", "category", "sub_category")

    df_orders_partitioned = df_orders_selected.repartition("customer_id", "product_id")
    df_customers_partitioned = df_customers_selected.repartition("customer_id")
    df_products_partitioned = df_products_selected.repartition("product_id")

    return df_orders_partitioned, df_customers_partitioned, df_products_partitioned

def join_ecomm_data(
    df_orders: DataFrame,
    df_customers: DataFrame,
    df_products: DataFrame
) -> DataFrame:
    """
    Performs an inner join on orders, customers, and products dataframes.
    Assumes inputs are already selected/partitioned as needed.
    """
    df_orders_customers_products_joined = df_orders \
        .join(broadcast(df_customers), "customer_id", "inner") \
        .join(broadcast(df_products), "product_id", "inner")
    return df_orders_customers_products_joined

def aggregate_profit(df_combined_data: DataFrame) -> DataFrame:
    """
    Aggregates profit by year, category, sub_category, and customer_id.
    """
    df_profit_agg = df_combined_data.groupBy(
        year("order_date").alias("order_year"),
        "category",
        "sub_category",
        "customer_id"
    ).agg(
        sum("profit").alias("total_profit")
    ).orderBy(
        "order_year",
        "category",
        "sub_category",
        "customer_id"
    )
    return df_profit_agg
