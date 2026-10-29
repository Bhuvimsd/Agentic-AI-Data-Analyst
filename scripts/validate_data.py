"""
scripts/validate_data.py
------------------------
Relational integrity, row count, constraint, and financial consistency validator
for the Agentic AI Data Analyst database.

Usage:
  python scripts/validate_data.py
  python scripts/validate_data.py --db-url "sqlite:///test_local.db"
"""

import argparse
import sys
from pathlib import Path
from decimal import Decimal
from tabulate import tabulate
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Ensure Windows console handles UTF-8 output gracefully
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.config import settings


def run_validation_checks(engine) -> bool:
    """
    Executes a comprehensive battery of data integrity checks.
    Returns True if all checks pass, False otherwise.
    """
    all_passed = True
    report_rows = []

    print("\n" + "=" * 80)
    print("AGENTIC AI DATA ANALYST - PHASE 1 DATA INTEGRITY VALIDATION SUITE")
    print("=" * 80)

    with engine.connect() as conn:
        # ----------------------------------------------------------------------
        # 1. Row Count Validation
        # ----------------------------------------------------------------------
        table_thresholds = {
            "customers": 500,
            "products": 20,
            "stores": 8,
            "orders": 2000,
            "order_items": 2000,
            "payments": 2000,
        }

        for table, min_expected in table_thresholds.items():
            count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            passed = count >= min_expected
            if not passed:
                all_passed = False
            report_rows.append([
                "Row Count",
                f"{table} >= {min_expected}",
                f"{count} rows",
                "PASS" if passed else "FAIL"
            ])

        # ----------------------------------------------------------------------
        # 2. Primary Key Uniqueness & Non-Null Validation
        # ----------------------------------------------------------------------
        pk_definitions = [
            ("customers", "customer_id"),
            ("products", "product_id"),
            ("stores", "store_id"),
            ("orders", "order_id"),
            ("order_items", "item_id"),
            ("payments", "payment_id"),
        ]

        for table, pk in pk_definitions:
            pk_check = conn.execute(text(f"""
                SELECT COUNT(*) - COUNT(DISTINCT {pk}) AS duplicate_count,
                       SUM(CASE WHEN {pk} IS NULL THEN 1 ELSE 0 END) AS null_count
                FROM {table}
            """)).fetchone()
            
            duplicates = pk_check[0] or 0
            nulls = pk_check[1] or 0
            passed = (duplicates == 0 and nulls == 0)
            if not passed:
                all_passed = False
            report_rows.append([
                "PK Integrity",
                f"{table}.{pk} unique & not null",
                f"dup={duplicates}, null={nulls}",
                "PASS" if passed else "FAIL"
            ])

        # ----------------------------------------------------------------------
        # 3. Foreign Key Orphan Checks
        # ----------------------------------------------------------------------
        fk_checks = [
            ("orders.customer_id -> customers", """
                SELECT COUNT(*) FROM orders o 
                LEFT JOIN customers c ON o.customer_id = c.customer_id 
                WHERE c.customer_id IS NULL
            """),
            ("orders.store_id -> stores", """
                SELECT COUNT(*) FROM orders o 
                LEFT JOIN stores s ON o.store_id = s.store_id 
                WHERE s.store_id IS NULL
            """),
            ("order_items.order_id -> orders", """
                SELECT COUNT(*) FROM order_items oi 
                LEFT JOIN orders o ON oi.order_id = o.order_id 
                WHERE o.order_id IS NULL
            """),
            ("order_items.product_id -> products", """
                SELECT COUNT(*) FROM order_items oi 
                LEFT JOIN products p ON oi.product_id = p.product_id 
                WHERE p.product_id IS NULL
            """),
            ("payments.order_id -> orders", """
                SELECT COUNT(*) FROM payments p 
                LEFT JOIN orders o ON p.order_id = o.order_id 
                WHERE o.order_id IS NULL
            """),
        ]

        for label, query in fk_checks:
            orphans = conn.execute(text(query)).scalar() or 0
            passed = orphans == 0
            if not passed:
                all_passed = False
            report_rows.append([
                "FK Integrity",
                label,
                f"{orphans} orphaned records",
                "PASS" if passed else "FAIL"
            ])

        # ----------------------------------------------------------------------
        # 4. Status and Domain Constraint Checks
        # ----------------------------------------------------------------------
        constraint_queries = [
            ("orders.status allowed values", """
                SELECT COUNT(*) FROM orders 
                WHERE status NOT IN ('Completed', 'Pending', 'Cancelled')
            """),
            ("payments.payment_status allowed values", """
                SELECT COUNT(*) FROM payments 
                WHERE payment_status NOT IN ('Success', 'Pending', 'Failed', 'Refunded')
            """),
            ("payments.payment_method allowed values", """
                SELECT COUNT(*) FROM payments 
                WHERE payment_method NOT IN ('UPI', 'Credit Card', 'Debit Card', 'Net Banking', 'Cash on Delivery')
            """),
            ("stores.region allowed values", """
                SELECT COUNT(*) FROM stores 
                WHERE region NOT IN ('North', 'South', 'East', 'West', 'Central')
            """),
            ("positive prices check", """
                SELECT COUNT(*) FROM products WHERE price <= 0
            """),
            ("positive quantity check", """
                SELECT COUNT(*) FROM order_items WHERE quantity <= 0 OR unit_price <= 0
            """),
        ]

        for label, query in constraint_queries:
            violations = conn.execute(text(query)).scalar() or 0
            passed = violations == 0
            if not passed:
                all_passed = False
            report_rows.append([
                "Constraint",
                label,
                f"{violations} violations",
                "PASS" if passed else "FAIL"
            ])

        # ----------------------------------------------------------------------
        # 5. Financial & Business Metric Verification
        # ----------------------------------------------------------------------
        # Total completed-order revenue
        completed_revenue_query = """
            SELECT COALESCE(SUM(oi.quantity * oi.unit_price), 0)
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.order_id
            WHERE o.status = 'Completed'
        """
        completed_rev = Decimal(str(conn.execute(text(completed_revenue_query)).scalar() or "0.00"))
        has_revenue = completed_rev > 0
        if not has_revenue:
            all_passed = False
        report_rows.append([
            "Financial",
            "Total Completed Revenue > 0",
            f"INR {completed_rev:,.2f}",
            "PASS" if has_revenue else "FAIL"
        ])

        # Verification of intentional payment anomalies
        anomaly_query = """
            SELECT COUNT(*)
            FROM orders o
            JOIN (
                SELECT order_id, ROUND(SUM(quantity * unit_price), 2) AS expected_total
                FROM order_items
                GROUP BY order_id
            ) oi ON o.order_id = oi.order_id
            JOIN payments p ON o.order_id = p.order_id
            WHERE o.status = 'Completed'
              AND (p.payment_status != 'Success' OR ROUND(p.amount, 2) != oi.expected_total)
        """
        anomaly_count = conn.execute(text(anomaly_query)).scalar() or 0
        passed = (anomaly_count == 2)
        report_rows.append([
            "Business Rules",
            "Completed Order vs Payment Anomaly",
            f"{anomaly_count} intentional anomalies tracked (Orders 100 & 250)",
            "PASS" if passed else "FAIL"
        ])

    # Print formatted validation report
    print(tabulate(
        report_rows,
        headers=["Category", "Validation Check", "Result Value", "Status"],
        tablefmt="grid"
    ))

    if all_passed:
        print("\n[SUCCESS] All relational and domain constraints passed with 100% integrity.")
    else:
        print("\n[FAILURE] One or more integrity checks failed. Inspect logs above.")

    return all_passed


def main():
    parser = argparse.ArgumentParser(description="Agentic AI Data Analyst - Data Integrity Validator")
    parser.add_argument("--db-url", type=str, default=None, help="Custom SQLAlchemy database connection URL")
    args = parser.parse_args()

    url = args.db_url or settings.DATABASE_URL
    print(f"Connecting to database: {url.split('@')[-1] if '@' in url else url}")
    engine = create_engine(url)

    success = run_validation_checks(engine)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
