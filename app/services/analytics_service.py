"""
app/services/analytics_service.py
---------------------------------
Controlled analytical query execution service and dynamic schema inspector.
Enforces query parameterization, row limits, type serialization, and safe error handling.
"""

import time
import logging
from decimal import Decimal
from datetime import datetime, date
from typing import Dict, Any, List, Optional
from sqlalchemy import text, inspect, Connection
from app.config import settings
from app.api.schemas import (
    PredefinedQueryID, QueryParameters, AnalyticsQueryResponse, 
    QueryExecutionMetadata, SchemaResponse, TableMetadata, ColumnMetadata
)

logger = logging.getLogger("agentic_ai.analytics_service")

# ------------------------------------------------------------------------------
# Approved Analytical Query Registry
# ------------------------------------------------------------------------------
APPROVED_QUERIES: Dict[PredefinedQueryID, Dict[str, Any]] = {
    PredefinedQueryID.TOTAL_REVENUE: {
        "title": "Total Completed Order Revenue",
        "description": "Calculates recognized gross revenue from completed orders.",
        "sql": """
            SELECT 
                COUNT(DISTINCT o.order_id) AS total_completed_orders,
                ROUND(SUM(oi.quantity * oi.unit_price), 2) AS total_revenue
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.order_id
            WHERE o.status = 'Completed'
        """,
        "default_limit": 1
    },
    PredefinedQueryID.TOP_PRODUCTS_BY_REVENUE: {
        "title": "Top Products by Revenue",
        "description": "Ranks products by total completed sales revenue.",
        "sql": """
            SELECT 
                p.product_id,
                p.product_name,
                p.category,
                SUM(oi.quantity) AS total_units_sold,
                ROUND(SUM(oi.quantity * oi.unit_price), 2) AS total_revenue
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.order_id
            JOIN products p ON oi.product_id = p.product_id
            WHERE o.status = 'Completed'
              AND (:category IS NULL OR p.category = :category)
            GROUP BY p.product_id, p.product_name, p.category
            ORDER BY total_revenue DESC
            LIMIT :limit
        """,
        "default_limit": 5
    },
    PredefinedQueryID.MONTHLY_REVENUE: {
        "title": "Monthly Revenue Trend",
        "description": "Chronological monthly sales volume and revenue totals.",
        "sql": """
            SELECT 
                SUBSTR(CAST(o.order_date AS VARCHAR), 1, 7) AS order_month,
                COUNT(DISTINCT o.order_id) AS total_orders,
                ROUND(SUM(oi.quantity * oi.unit_price), 2) AS monthly_revenue
            FROM orders o
            JOIN order_items oi ON o.order_id = oi.order_id
            WHERE o.status = 'Completed'
            GROUP BY SUBSTR(CAST(o.order_date AS VARCHAR), 1, 7)
            ORDER BY order_month ASC
            LIMIT :limit
        """,
        "default_limit": 24
    },
    PredefinedQueryID.TOP_CUSTOMERS_BY_SPEND: {
        "title": "Top Customers by Total Spending",
        "description": "Identifies highest-value customers by completed order spend.",
        "sql": """
            SELECT 
                c.customer_id,
                c.customer_name,
                c.city,
                COUNT(DISTINCT o.order_id) AS completed_orders_count,
                ROUND(SUM(oi.quantity * oi.unit_price), 2) AS total_spend
            FROM customers c
            JOIN orders o ON c.customer_id = o.customer_id
            JOIN order_items oi ON o.order_id = oi.order_id
            WHERE o.status = 'Completed'
            GROUP BY c.customer_id, c.customer_name, c.city
            ORDER BY total_spend DESC
            LIMIT :limit
        """,
        "default_limit": 5
    },
    PredefinedQueryID.REVENUE_BY_REGION: {
        "title": "Revenue by Store Region",
        "description": "Breakdown of completed revenue and order volume across commercial zones.",
        "sql": """
            SELECT 
                s.region,
                COUNT(DISTINCT s.store_id) AS store_count,
                COUNT(DISTINCT o.order_id) AS total_orders,
                ROUND(SUM(oi.quantity * oi.unit_price), 2) AS regional_revenue
            FROM stores s
            JOIN orders o ON s.store_id = o.store_id
            JOIN order_items oi ON o.order_id = oi.order_id
            WHERE o.status = 'Completed'
              AND (:region IS NULL OR s.region = :region)
            GROUP BY s.region
            ORDER BY regional_revenue DESC
            LIMIT :limit
        """,
        "default_limit": 10
    },
    PredefinedQueryID.AVERAGE_ORDER_VALUE: {
        "title": "Average Order Value (AOV)",
        "description": "Computes AOV, minimum, and maximum order values for completed orders.",
        "sql": """
            WITH order_totals AS (
                SELECT 
                    o.order_id,
                    ROUND(SUM(oi.quantity * oi.unit_price), 2) AS order_total
                FROM orders o
                JOIN order_items oi ON o.order_id = oi.order_id
                WHERE o.status = 'Completed'
                GROUP BY o.order_id
            )
            SELECT 
                COUNT(order_id) AS completed_orders_count,
                ROUND(AVG(order_total), 2) AS average_order_value,
                ROUND(MIN(order_total), 2) AS min_order_value,
                ROUND(MAX(order_total), 2) AS max_order_value
            FROM order_totals
        """,
        "default_limit": 1
    },
    PredefinedQueryID.PRODUCTS_NEVER_ORDERED: {
        "title": "Unordered Inventory Audit",
        "description": "Lists merchandise currently in catalog with zero historical orders.",
        "sql": """
            SELECT 
                p.product_id,
                p.product_name,
                p.category,
                ROUND(p.price, 2) AS price
            FROM products p
            LEFT JOIN order_items oi ON p.product_id = oi.product_id
            WHERE oi.item_id IS NULL
            ORDER BY p.price DESC
            LIMIT :limit
        """,
        "default_limit": 50
    },
    PredefinedQueryID.REPEAT_CUSTOMERS: {
        "title": "Repeat Customers Cohort",
        "description": "Customers who have placed more than one order.",
        "sql": """
            SELECT 
                c.customer_id,
                c.customer_name,
                c.city,
                COUNT(o.order_id) AS total_orders_placed,
                COUNT(CASE WHEN o.status = 'Completed' THEN 1 END) AS completed_orders
            FROM customers c
            JOIN orders o ON c.customer_id = o.customer_id
            GROUP BY c.customer_id, c.customer_name, c.city
            HAVING COUNT(o.order_id) > 1
            ORDER BY total_orders_placed DESC
            LIMIT :limit
        """,
        "default_limit": 50
    },
    PredefinedQueryID.PAYMENT_ANOMALIES: {
        "title": "Payment Reconciliation Anomalies",
        "description": "Detects discrepancy between calculated order total and recorded payment status/amount.",
        "sql": """
            WITH order_item_aggregates AS (
                SELECT 
                    order_id,
                    ROUND(SUM(quantity * unit_price), 2) AS calculated_order_total
                FROM order_items
                GROUP BY order_id
            )
            SELECT 
                o.order_id,
                o.status AS order_status,
                oia.calculated_order_total,
                ROUND(p.amount, 2) AS payment_amount,
                p.payment_status,
                p.payment_method
            FROM orders o
            JOIN order_item_aggregates oia ON o.order_id = oia.order_id
            JOIN payments p ON o.order_id = p.order_id
            WHERE (o.status = 'Completed' AND (p.payment_status != 'Success' OR ROUND(p.amount, 2) != oia.calculated_order_total))
               OR (o.status = 'Cancelled' AND p.payment_status NOT IN ('Refunded', 'Failed'))
            ORDER BY o.order_id ASC
            LIMIT :limit
        """,
        "default_limit": 50
    },
    PredefinedQueryID.CATEGORY_SALES: {
        "title": "Category Sales & Market Share",
        "description": "Sales volume, revenue, and percentage share across product categories.",
        "sql": """
            WITH category_metrics AS (
                SELECT 
                    p.category,
                    COUNT(DISTINCT p.product_id) AS product_count,
                    SUM(oi.quantity) AS units_sold,
                    ROUND(SUM(oi.quantity * oi.unit_price), 2) AS category_revenue
                FROM products p
                JOIN order_items oi ON p.product_id = oi.product_id
                JOIN orders o ON oi.order_id = o.order_id
                WHERE o.status = 'Completed'
                GROUP BY p.category
            )
            SELECT 
                category,
                product_count,
                units_sold,
                category_revenue,
                ROUND(
                    (category_revenue / SUM(category_revenue) OVER ()) * 100, 
                    2
                ) AS revenue_percentage_share
            FROM category_metrics
            ORDER BY category_revenue DESC
            LIMIT :limit
        """,
        "default_limit": 20
    }
}


def serialize_cell_value(val: Any) -> Any:
    """Converts Decimal, Date, and DateTime objects to JSON-serializable primitives."""
    if isinstance(val, Decimal):
        return float(val)
    elif isinstance(val, (datetime, date)):
        return val.isoformat()
    return val


def execute_predefined_query(
    conn: Connection,
    query_id: PredefinedQueryID,
    params: Optional[QueryParameters] = None
) -> AnalyticsQueryResponse:
    """
    Executes an approved analytical query with validated parameters,
    measuring execution latency and returning structured results.
    """
    if query_id not in APPROVED_QUERIES:
        raise ValueError(f"Query ID '{query_id}' is not in the approved analytical registry.")
        
    query_info = APPROVED_QUERIES[query_id]
    user_params = params or QueryParameters()

    # Determine and bound limit parameter
    applied_limit = user_params.limit or query_info["default_limit"]
    applied_limit = min(applied_limit, settings.MAX_ROW_LIMIT)

    # Prepare parameterized dictionary
    query_bindings = {
        "limit": applied_limit,
        "category": user_params.category,
        "region": user_params.region,
        "start_date": user_params.start_date,
        "end_date": user_params.end_date,
    }

    start_time = time.perf_counter()
    try:
        cursor_result = conn.execute(text(query_info["sql"]), query_bindings)
        columns = list(cursor_result.keys())
        raw_rows = cursor_result.fetchall()
        
        # Serialize each row to JSON-compatible dictionary
        serialized_data = [
            {col: serialize_cell_value(val) for col, val in zip(columns, row)}
            for row in raw_rows
        ]
        execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return AnalyticsQueryResponse(
            success=True,
            query_id=query_id.value,
            title=query_info["title"],
            description=query_info["description"],
            metadata=QueryExecutionMetadata(
                query_id=query_id.value,
                execution_time_ms=execution_time_ms,
                row_count=len(serialized_data),
                applied_limit=applied_limit,
                statement_timeout_seconds=settings.QUERY_TIMEOUT_SECONDS
            ),
            columns=columns,
            data=serialized_data,
            error=None
        )
    except Exception as e:
        execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.error(f"Error executing query {query_id}: {str(e)}")
        # Safe error masking to prevent DB credentials/internal leakage
        raise RuntimeError("Failed to execute analytical query due to a database processing error.")


def get_database_schema(conn: Connection) -> SchemaResponse:
    """
    Dynamically inspects the approved tables and returns their structural schema metadata.
    """
    inspector = inspect(conn)
    approved_tables = ["customers", "products", "stores", "orders", "order_items", "payments"]
    
    table_metadata_list = []
    for table_name in approved_tables:
        try:
            # Row count
            row_count = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar() or 0
        except Exception:
            row_count = 0

        columns_info = inspector.get_columns(table_name)
        pk_info = inspector.get_pk_constraint(table_name)
        pk_cols = set(pk_info.get("constrained_columns", []) if pk_info else [])
        
        fk_info = inspector.get_foreign_keys(table_name)
        fk_map = {}
        for fk in fk_info:
            target = f"{fk.get('referred_table')}({','.join(fk.get('referred_columns', []))})"
            for col in fk.get("constrained_columns", []):
                fk_map[col] = target

        columns = []
        for col in columns_info:
            c_name = col["name"]
            columns.append(ColumnMetadata(
                column_name=c_name,
                data_type=str(col["type"]),
                is_nullable=bool(col.get("nullable", True)),
                is_primary_key=c_name in pk_cols,
                is_foreign_key=c_name in fk_map,
                foreign_key_target=fk_map.get(c_name)
            ))

        table_metadata_list.append(TableMetadata(
            table_name=table_name,
            row_count=row_count,
            columns=columns
        ))

    db_name = conn.engine.url.database or "agentic_ai_analytics"
    return SchemaResponse(
        status="success",
        database_name=db_name,
        total_tables=len(table_metadata_list),
        tables=table_metadata_list
    )
