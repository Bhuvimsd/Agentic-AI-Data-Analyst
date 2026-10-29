"""
app/llm/schema_context.py
-------------------------
Schema Context Builder for Text-to-SQL generation.
Provides schema grounding by exposing strictly approved tables, columns,
relational foreign keys, and fundamental business accounting rules.
"""

from typing import List, Dict, Any


def get_analytical_schema_prompt_context() -> str:
    """
    Returns a comprehensive, formatted schema grounding prompt string
    for LLM system prompts.
    """
    return """
### DATABASE ENGINE: PostgreSQL 14+
You have access to the following 6 analytical tables ONLY:

1. customers (Customer demographics)
   - customer_id (INT, PRIMARY KEY): Unique customer identifier.
   - customer_name (VARCHAR): Customer full name.
   - city (VARCHAR): Residential city (e.g., 'Bengaluru', 'Mumbai', 'Delhi', 'Hyderabad').
   - created_at (TIMESTAMPTZ): Account registration timestamp.

2. products (Merchandise catalog)
   - product_id (INT, PRIMARY KEY): Unique product SKU identifier.
   - product_name (VARCHAR): Product title.
   - category (VARCHAR): Merchandise category ('Electronics', 'Apparel', 'Home & Kitchen', 'Grocery', 'Fitness').
   - price (NUMERIC(10, 2)): Current catalog price in INR.

3. stores (Physical retail & fulfillment hubs)
   - store_id (INT, PRIMARY KEY): Unique store identifier.
   - store_name (VARCHAR): Store flagship name and neighborhood.
   - region (VARCHAR): Commercial zone ('North', 'South', 'East', 'West', 'Central').

4. orders (Order headers and lifecycle status)
   - order_id (INT, PRIMARY KEY): Unique order ID.
   - customer_id (INT, FOREIGN KEY -> customers.customer_id): Purchasing customer.
   - store_id (INT, FOREIGN KEY -> stores.store_id): Fulfilling store.
   - order_date (TIMESTAMPTZ): Transaction timestamp.
   - status (VARCHAR): Order state ('Completed', 'Pending', 'Cancelled').

5. order_items (Granular purchased line items)
   - item_id (INT, PRIMARY KEY): Unique line item ID.
   - order_id (INT, FOREIGN KEY -> orders.order_id): Parent order.
   - product_id (INT, FOREIGN KEY -> products.product_id): Purchased SKU.
   - quantity (INT): Number of units purchased (always > 0).
   - unit_price (NUMERIC(10, 2)): Historical price at purchase in INR.

6. payments (Settlement ledger)
   - payment_id (INT, PRIMARY KEY): Unique payment record ID.
   - order_id (INT, FOREIGN KEY -> orders.order_id): Associated order.
   - amount (NUMERIC(10, 2)): Payment amount in INR.
   - payment_method (VARCHAR): 'UPI', 'Credit Card', 'Debit Card', 'Net Banking', 'Cash on Delivery'.
   - payment_status (VARCHAR): 'Success', 'Pending', 'Failed', 'Refunded'.

### CRITICAL BUSINESS & FINANCIAL RULES:
1. RECOGNIZED REVENUE DEFINITION:
   Revenue is strictly defined as SUM(oi.quantity * oi.unit_price) WHERE orders.status = 'Completed'.
   Never calculate revenue without filtering for orders.status = 'Completed' unless the user explicitly requests pending or all orders.
2. HISTORICAL PRICE PRESERVATION:
   Never join back to products.price to compute revenue or order totals! Always use order_items.unit_price because catalog prices fluctuate.
3. AVERAGE ORDER VALUE (AOV):
   AOV is computed as (Total Completed Revenue / Total Completed Orders), or the AVG() of order totals.
4. REFUNDS:
   Cancelled orders may have refunded payments. They are excluded from recognized revenue by filtering orders.status = 'Completed'.
5. SCHEMA GROUNDING & NON-EXISTENT ENTITIES:
   - There are NO tables named 'discounts', 'employees', 'coupons', 'reviews', 'inventory', 'salaries'.
   - There are NO columns named 'profit', 'discount', 'margin', 'cost', 'email', 'phone'.
   - If the user asks for a non-existent metric or table, set needs_clarification=True and explain what is missing.
6. SECURITY & IMMUTABILITY:
   - ONLY SELECT statements are permitted.
   - NEVER generate INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, or GRANT.
   - If the user asks to modify data or execute system commands, set is_safe_query=False and rejection_reason='Modifications and system commands are strictly forbidden.'
""".strip()


ALLOWED_TABLES: List[str] = [
    "customers", "products", "stores", "orders", "order_items", "payments"
]

ALLOWED_COLUMNS: Dict[str, List[str]] = {
    "customers": ["customer_id", "customer_name", "city", "created_at"],
    "products": ["product_id", "product_name", "category", "price"],
    "stores": ["store_id", "store_name", "region"],
    "orders": ["order_id", "customer_id", "store_id", "order_date", "status"],
    "order_items": ["item_id", "order_id", "product_id", "quantity", "unit_price"],
    "payments": ["payment_id", "order_id", "amount", "payment_method", "payment_status"]
}
