"""
tests/test_data_integrity.py
-----------------------------
Comprehensive automated test suite for Phase 1:
- Table row count thresholds
- Primary key uniqueness & non-null constraints
- Foreign key relational integrity (no orphaned children)
- Domain & CHECK constraints
- Financial metrics & business rules
- Verification of all 10 analytical business queries
- Idempotency test (re-running the data loader preserves deterministic counts)
"""

import os
import sys
from pathlib import Path
from decimal import Decimal
import pytest
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import settings
from scripts.load_data import init_schema, seed_data
from scripts.generate_data import generate_synthetic_dataset


@pytest.fixture(scope="session")
def db_engine():
    """
    Session-scoped database engine fixture.
    Uses SQLite in-memory or file database for test isolation,
    or can test against PostgreSQL if DATABASE_URL is configured.
    """
    test_db_url = os.getenv("TEST_DATABASE_URL", "sqlite:///test_pytest_analytics.db")
    engine = create_engine(test_db_url, echo=False)
    
    # Initialize fresh schema and seed data once for the test session
    init_schema(engine)
    dataset = generate_synthetic_dataset(num_customers=500, num_orders=2200)
    seed_data(engine, dataset=dataset)
    
    yield engine
    
    # Cleanup file if local SQLite was used
    if "sqlite:///" in test_db_url and ":memory:" not in test_db_url:
        db_file = test_db_url.replace("sqlite:///", "")
        if os.path.exists(db_file):
            try:
                os.remove(db_file)
            except Exception:
                pass


# ------------------------------------------------------------------------------
# 1. Row Count Tests
# ------------------------------------------------------------------------------
def test_minimum_row_counts(db_engine):
    """Verifies that all tables meet or exceed minimum row count requirements."""
    thresholds = {
        "customers": 500,
        "products": 20,
        "stores": 8,
        "orders": 2000,
        "order_items": 2000,
        "payments": 2000,
    }
    with db_engine.connect() as conn:
        for table, min_count in thresholds.items():
            count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            assert count >= min_count, f"Table '{table}' has {count} rows, expected >= {min_count}"


# ------------------------------------------------------------------------------
# 2. Primary Key Uniqueness & Non-Null Tests
# ------------------------------------------------------------------------------
@pytest.mark.parametrize("table,pk_col", [
    ("customers", "customer_id"),
    ("products", "product_id"),
    ("stores", "store_id"),
    ("orders", "order_id"),
    ("order_items", "item_id"),
    ("payments", "payment_id"),
])
def test_primary_key_uniqueness_and_not_null(db_engine, table, pk_col):
    """Asserts that primary keys contain zero duplicates and zero NULLs."""
    with db_engine.connect() as conn:
        row = conn.execute(text(f"""
            SELECT COUNT(*) - COUNT(DISTINCT {pk_col}) AS dup_count,
                   SUM(CASE WHEN {pk_col} IS NULL THEN 1 ELSE 0 END) AS null_count
            FROM {table}
        """)).fetchone()
        assert row[0] == 0, f"Found {row[0]} duplicate primary keys in {table}.{pk_col}"
        assert row[1] == 0, f"Found {row[1]} NULL primary keys in {table}.{pk_col}"


# ------------------------------------------------------------------------------
# 3. Foreign Key Relational Integrity Tests
# ------------------------------------------------------------------------------
def test_foreign_key_orders_to_customers(db_engine):
    """Verify orders reference valid customer IDs."""
    with db_engine.connect() as conn:
        orphans = conn.execute(text("""
            SELECT COUNT(*) FROM orders o 
            LEFT JOIN customers c ON o.customer_id = c.customer_id 
            WHERE c.customer_id IS NULL
        """)).scalar()
        assert orphans == 0, f"Found {orphans} orphaned orders with invalid customer_id"


def test_foreign_key_orders_to_stores(db_engine):
    """Verify orders reference valid store IDs."""
    with db_engine.connect() as conn:
        orphans = conn.execute(text("""
            SELECT COUNT(*) FROM orders o 
            LEFT JOIN stores s ON o.store_id = s.store_id 
            WHERE s.store_id IS NULL
        """)).scalar()
        assert orphans == 0, f"Found {orphans} orphaned orders with invalid store_id"


def test_foreign_key_order_items_to_orders(db_engine):
    """Verify order items reference valid order IDs."""
    with db_engine.connect() as conn:
        orphans = conn.execute(text("""
            SELECT COUNT(*) FROM order_items oi 
            LEFT JOIN orders o ON oi.order_id = o.order_id 
            WHERE o.order_id IS NULL
        """)).scalar()
        assert orphans == 0, f"Found {orphans} orphaned order items with invalid order_id"


def test_foreign_key_order_items_to_products(db_engine):
    """Verify order items reference valid product IDs."""
    with db_engine.connect() as conn:
        orphans = conn.execute(text("""
            SELECT COUNT(*) FROM order_items oi 
            LEFT JOIN products p ON oi.product_id = p.product_id 
            WHERE p.product_id IS NULL
        """)).scalar()
        assert orphans == 0, f"Found {orphans} orphaned order items with invalid product_id"


def test_foreign_key_payments_to_orders(db_engine):
    """Verify payments reference valid order IDs."""
    with db_engine.connect() as conn:
        orphans = conn.execute(text("""
            SELECT COUNT(*) FROM payments p 
            LEFT JOIN orders o ON p.order_id = o.order_id 
            WHERE o.order_id IS NULL
        """)).scalar()
        assert orphans == 0, f"Found {orphans} orphaned payments with invalid order_id"


# ------------------------------------------------------------------------------
# 4. Domain & Check Constraints
# ------------------------------------------------------------------------------
def test_order_statuses(db_engine):
    """Verify order statuses are strictly 'Completed', 'Pending', or 'Cancelled'."""
    with db_engine.connect() as conn:
        violations = conn.execute(text("""
            SELECT COUNT(*) FROM orders 
            WHERE status NOT IN ('Completed', 'Pending', 'Cancelled')
        """)).scalar()
        assert violations == 0


def test_payment_statuses(db_engine):
    """Verify payment statuses are strictly 'Success', 'Pending', 'Failed', or 'Refunded'."""
    with db_engine.connect() as conn:
        violations = conn.execute(text("""
            SELECT COUNT(*) FROM payments 
            WHERE payment_status NOT IN ('Success', 'Pending', 'Failed', 'Refunded')
        """)).scalar()
        assert violations == 0


def test_positive_financial_values(db_engine):
    """Verify positive prices, positive quantities, and non-negative payments."""
    with db_engine.connect() as conn:
        bad_prices = conn.execute(text("SELECT COUNT(*) FROM products WHERE price <= 0")).scalar()
        assert bad_prices == 0
        bad_items = conn.execute(text("SELECT COUNT(*) FROM order_items WHERE quantity <= 0 OR unit_price <= 0")).scalar()
        assert bad_items == 0
        bad_payments = conn.execute(text("SELECT COUNT(*) FROM payments WHERE amount < 0")).scalar()
        assert bad_payments == 0


# ------------------------------------------------------------------------------
# 5. Business Rules & Financial Consistency
# ------------------------------------------------------------------------------
def test_revenue_definition_and_refunds(db_engine):
    """
    Validates our business revenue definition:
    Revenue = SUM(quantity * unit_price) for completed orders.
    Refunded payments from cancelled orders must NOT be included in revenue.
    """
    with db_engine.connect() as conn:
        completed_rev = conn.execute(text("""
            SELECT SUM(oi.quantity * oi.unit_price) 
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.order_id
            WHERE o.status = 'Completed'
        """)).scalar()
        assert completed_rev > 0, "Completed order revenue must be greater than zero"

        # Verify that cancelled orders with refunded payments exist and are excluded
        refunded_count = conn.execute(text("""
            SELECT COUNT(*) FROM payments p
            JOIN orders o ON p.order_id = o.order_id
            WHERE o.status = 'Cancelled' AND p.payment_status = 'Refunded'
        """)).scalar()
        assert refunded_count > 0, "Dataset should have cancelled orders with refunded payments"


def test_intentional_payment_anomalies(db_engine):
    """
    Verifies that the deliberate payment anomalies (Orders 100 and 250)
    are present and detectable by the reconciliation query.
    """
    with db_engine.connect() as conn:
        anomalies = conn.execute(text("""
            WITH oia AS (
                SELECT order_id, ROUND(SUM(quantity * unit_price), 2) AS expected_total
                FROM order_items
                GROUP BY order_id
            )
            SELECT o.order_id, p.payment_status, p.amount, oia.expected_total
            FROM orders o
            JOIN oia ON o.order_id = oia.order_id
            JOIN payments p ON o.order_id = p.order_id
            WHERE o.status = 'Completed'
              AND (p.payment_status != 'Success' OR ROUND(p.amount, 2) != oia.expected_total)
        """)).fetchall()
        assert len(anomalies) == 2, f"Expected 2 tracked anomalies, found {len(anomalies)}"
        anomaly_order_ids = {a[0] for a in anomalies}
        assert anomaly_order_ids == {100, 250}


# ------------------------------------------------------------------------------
# 6. Verification of the 10 Business Analytical Queries
# ------------------------------------------------------------------------------
def test_query_1_total_completed_revenue(db_engine):
    with db_engine.connect() as conn:
        val = conn.execute(text("""
            SELECT SUM(oi.quantity * oi.unit_price) 
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.order_id
            WHERE o.status = 'Completed'
        """)).scalar()
        assert val is not None and val > 1000000


def test_query_2_top_5_products_by_revenue(db_engine):
    with db_engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT p.product_name, SUM(oi.quantity * oi.unit_price) AS rev
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.order_id
            JOIN products p ON oi.product_id = p.product_id
            WHERE o.status = 'Completed'
            GROUP BY p.product_id, p.product_name
            ORDER BY rev DESC
            LIMIT 5
        """)).fetchall()
        assert len(rows) == 5
        # Verify descending order
        revenues = [r[1] for r in rows]
        assert revenues == sorted(revenues, reverse=True)


def test_query_3_monthly_revenue(db_engine):
    with db_engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT SUBSTR(o.order_date, 1, 7) AS order_month, 
                   COUNT(DISTINCT o.order_id) AS total_orders, 
                   SUM(oi.quantity * oi.unit_price) AS monthly_revenue
            FROM orders o
            JOIN order_items oi ON o.order_id = oi.order_id
            WHERE o.status = 'Completed'
            GROUP BY SUBSTR(o.order_date, 1, 7)
            ORDER BY order_month ASC
        """)).fetchall()
        assert len(rows) >= 12, "Should cover over 12 months of analytical order history"


def test_query_4_top_5_customers_by_spending(db_engine):
    with db_engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT c.customer_name, SUM(oi.quantity * oi.unit_price) AS spend
            FROM customers c
            JOIN orders o ON c.customer_id = o.customer_id
            JOIN order_items oi ON o.order_id = oi.order_id
            WHERE o.status = 'Completed'
            GROUP BY c.customer_id, c.customer_name
            ORDER BY spend DESC
            LIMIT 5
        """)).fetchall()
        assert len(rows) == 5


def test_query_5_revenue_by_store_region(db_engine):
    with db_engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT s.region, SUM(oi.quantity * oi.unit_price) AS regional_revenue
            FROM stores s
            JOIN orders o ON s.store_id = o.store_id
            JOIN order_items oi ON o.order_id = oi.order_id
            WHERE o.status = 'Completed'
            GROUP BY s.region
            ORDER BY regional_revenue DESC
        """)).fetchall()
        regions = {r[0] for r in rows}
        assert {"North", "South", "East", "West", "Central"}.issubset(regions)


def test_query_6_average_completed_order_value(db_engine):
    with db_engine.connect() as conn:
        aov = conn.execute(text("""
            WITH order_totals AS (
                SELECT o.order_id, SUM(oi.quantity * oi.unit_price) AS order_total
                FROM orders o
                JOIN order_items oi ON o.order_id = oi.order_id
                WHERE o.status = 'Completed'
                GROUP BY o.order_id
            )
            SELECT ROUND(AVG(order_total), 2) FROM order_totals
        """)).scalar()
        assert aov is not None and aov > 0


def test_query_7_products_never_ordered(db_engine):
    with db_engine.connect() as conn:
        never_ordered = conn.execute(text("""
            SELECT p.product_name 
            FROM products p
            LEFT JOIN order_items oi ON p.product_id = oi.product_id
            WHERE oi.item_id IS NULL
        """)).fetchall()
        assert len(never_ordered) >= 2
        names = {n[0] for n in never_ordered}
        assert "Vintage Turntable Vinyl Record Player" in names
        assert "Titanium Expedition Camping Stove" in names


def test_query_8_customers_with_multiple_orders(db_engine):
    with db_engine.connect() as conn:
        multi_order_customers = conn.execute(text("""
            SELECT c.customer_id, COUNT(o.order_id) AS total_orders
            FROM customers c
            JOIN orders o ON c.customer_id = o.customer_id
            GROUP BY c.customer_id
            HAVING COUNT(o.order_id) > 1
        """)).fetchall()
        assert len(multi_order_customers) > 200, "Should have numerous repeat customers"


def test_query_9_orders_with_inconsistent_payment_records(db_engine):
    with db_engine.connect() as conn:
        anomalies = conn.execute(text("""
            WITH oia AS (
                SELECT order_id, ROUND(SUM(quantity * unit_price), 2) AS expected_total
                FROM order_items
                GROUP BY order_id
            )
            SELECT o.order_id
            FROM orders o
            JOIN oia ON o.order_id = oia.order_id
            JOIN payments p ON o.order_id = p.order_id
            WHERE o.status = 'Completed'
              AND (p.payment_status != 'Success' OR ROUND(p.amount, 2) != oia.expected_total)
        """)).fetchall()
        assert len(anomalies) == 2


def test_query_10_sales_by_product_category(db_engine):
    with db_engine.connect() as conn:
        rows = conn.execute(text("""
            WITH cat_metrics AS (
                SELECT p.category, SUM(oi.quantity * oi.unit_price) AS cat_rev
                FROM products p
                JOIN order_items oi ON p.product_id = oi.product_id
                JOIN orders o ON oi.order_id = o.order_id
                WHERE o.status = 'Completed'
                GROUP BY p.category
            )
            SELECT category, cat_rev, ROUND((cat_rev / SUM(cat_rev) OVER ()) * 100, 2) AS pct
            FROM cat_metrics
            ORDER BY cat_rev DESC
        """)).fetchall()
        assert len(rows) >= 5
        total_pct = sum(r[2] for r in rows)
        assert 99.0 <= total_pct <= 101.0  # Percentage sums to ~100%


# ------------------------------------------------------------------------------
# 7. Idempotency Test (Re-running data loader)
# ------------------------------------------------------------------------------
def test_data_loader_idempotency(db_engine):
    """
    Rerunning the data loading pipeline must not duplicate records,
    corrupt sequences, or violate primary/foreign keys.
    """
    dataset = generate_synthetic_dataset(num_customers=500, num_orders=2200)
    # Re-seed data over existing database
    seed_data(db_engine, dataset=dataset)
    
    with db_engine.connect() as conn:
        cust_count = conn.execute(text("SELECT COUNT(*) FROM customers")).scalar()
        ord_count = conn.execute(text("SELECT COUNT(*) FROM orders")).scalar()
        item_count = conn.execute(text("SELECT COUNT(*) FROM order_items")).scalar()
        
        assert cust_count == 500, f"Expected 500 customers after re-seeding, got {cust_count}"
        assert ord_count == 2200, f"Expected 2200 orders after re-seeding, got {ord_count}"
        assert item_count == 3639, f"Expected 3639 items after re-seeding, got {item_count}"
