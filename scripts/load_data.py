"""
scripts/load_data.py
--------------------
Database loader and schema migration utility for Agentic AI Data Analyst.
Provides idempotent schema creation and batch data seeding using SQLAlchemy 2.0.

Usage:
  python scripts/load_data.py --reset
  python scripts/load_data.py --init-schema
  python scripts/load_data.py --seed
  python scripts/load_data.py --db-url "sqlite:///agentic_ai_analytics.db" --reset
"""

import argparse
import os
import sys
from pathlib import Path
from decimal import Decimal
from typing import Optional

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import (
    create_engine, text, MetaData, Table, Column, Integer, String, 
    Numeric, DateTime, ForeignKey, CheckConstraint, Index
)
from src.config import settings
from scripts.generate_data import generate_synthetic_dataset


def get_engine(db_url: Optional[str] = None):
    """Creates a SQLAlchemy engine from config or provided override."""
    url = db_url or settings.DATABASE_URL
    return create_engine(url, echo=False)


def execute_sql_file(engine, file_path: Path):
    """Executes a multi-statement SQL script file safely within a transaction."""
    print(f"Executing SQL file: {file_path.name}...")
    with open(file_path, "r", encoding="utf-8") as f:
        sql_content = f.read()

    # Split statements carefully (by semicolon at the end of lines)
    statements = [stmt.strip() for stmt in sql_content.split(";") if stmt.strip()]

    with engine.begin() as conn:
        for stmt in statements:
            # Skip pure comments or empty blocks
            clean_stmt = "\n".join(
                line for line in stmt.splitlines() 
                if not line.strip().startswith("--")
            ).strip()
            if clean_stmt:
                conn.execute(text(clean_stmt))
    print(f"Successfully executed {file_path.name}.")


def define_schema_metadata(is_sqlite: bool = False) -> MetaData:
    """
    Defines database metadata using SQLAlchemy Core.
    Works natively across both PostgreSQL and SQLite.
    """
    metadata = MetaData()

    customers = Table(
        "customers",
        metadata,
        Column("customer_id", Integer, primary_key=True, autoincrement=True),
        Column("customer_name", String(150), nullable=False),
        Column("city", String(100), nullable=False),
        Column("created_at", String if is_sqlite else DateTime(timezone=True), nullable=False),
        Index("idx_customers_city", "city"),
    )

    products = Table(
        "products",
        metadata,
        Column("product_id", Integer, primary_key=True, autoincrement=True),
        Column("product_name", String(200), nullable=False),
        Column("category", String(100), nullable=False),
        Column("price", Numeric(10, 2), nullable=False),
        CheckConstraint("price > 0", name="chk_products_price_positive"),
        Index("idx_products_category", "category"),
    )

    stores = Table(
        "stores",
        metadata,
        Column("store_id", Integer, primary_key=True, autoincrement=True),
        Column("store_name", String(150), nullable=False),
        Column("region", String(50), nullable=False),
        CheckConstraint("region IN ('North', 'South', 'East', 'West', 'Central')", name="chk_stores_region"),
        Index("idx_stores_region", "region"),
    )

    orders = Table(
        "orders",
        metadata,
        Column("order_id", Integer, primary_key=True, autoincrement=True),
        Column("customer_id", Integer, ForeignKey("customers.customer_id", ondelete="RESTRICT"), nullable=False),
        Column("store_id", Integer, ForeignKey("stores.store_id", ondelete="RESTRICT"), nullable=False),
        Column("order_date", String if is_sqlite else DateTime(timezone=True), nullable=False),
        Column("status", String(20), nullable=False),
        CheckConstraint("status IN ('Completed', 'Pending', 'Cancelled')", name="chk_orders_status"),
        Index("idx_orders_customer_id", "customer_id"),
        Index("idx_orders_store_id", "store_id"),
        Index("idx_orders_status", "status"),
    )

    order_items = Table(
        "order_items",
        metadata,
        Column("item_id", Integer, primary_key=True, autoincrement=True),
        Column("order_id", Integer, ForeignKey("orders.order_id", ondelete="CASCADE"), nullable=False),
        Column("product_id", Integer, ForeignKey("products.product_id", ondelete="RESTRICT"), nullable=False),
        Column("quantity", Integer, nullable=False),
        Column("unit_price", Numeric(10, 2), nullable=False),
        CheckConstraint("quantity > 0", name="chk_order_items_quantity_positive"),
        CheckConstraint("unit_price > 0", name="chk_order_items_unit_price_positive"),
        Index("idx_order_items_order_id", "order_id"),
        Index("idx_order_items_product_id", "product_id"),
    )

    payments = Table(
        "payments",
        metadata,
        Column("payment_id", Integer, primary_key=True, autoincrement=True),
        Column("order_id", Integer, ForeignKey("orders.order_id", ondelete="CASCADE"), nullable=False),
        Column("amount", Numeric(10, 2), nullable=False),
        Column("payment_method", String(50), nullable=False),
        Column("payment_status", String(20), nullable=False),
        CheckConstraint("amount >= 0", name="chk_payments_amount_non_negative"),
        CheckConstraint(
            "payment_method IN ('UPI', 'Credit Card', 'Debit Card', 'Net Banking', 'Cash on Delivery')",
            name="chk_payments_method"
        ),
        CheckConstraint(
            "payment_status IN ('Success', 'Pending', 'Failed', 'Refunded')",
            name="chk_payments_status"
        ),
        Index("idx_payments_order_id", "order_id"),
        Index("idx_payments_status", "payment_status"),
    )

    return metadata


def init_schema(engine):
    """
    Idempotently drops and recreates all database tables and indexes.
    If PostgreSQL, executes sql/schema.sql.
    If SQLite or generic engine, uses SQLAlchemy Core metadata.
    """
    is_postgres = "postgresql" in engine.url.drivername
    schema_sql_path = PROJECT_ROOT / "sql" / "schema.sql"

    if is_postgres and schema_sql_path.exists():
        print("Initializing schema using PostgreSQL DDL script...")
        execute_sql_file(engine, schema_sql_path)
    else:
        print(f"Initializing schema using SQLAlchemy metadata for dialect: {engine.url.drivername}...")
        metadata = define_schema_metadata(is_sqlite=("sqlite" in engine.url.drivername))
        metadata.drop_all(engine)
        metadata.create_all(engine)
    print("Schema initialization complete.")


def seed_data(engine, dataset: Optional[dict] = None):
    """
    Idempotently seeds synthetic records into the database in relational order.
    """
    if dataset is None:
        dataset = generate_synthetic_dataset(
            num_customers=settings.NUM_CUSTOMERS,
            num_orders=settings.NUM_ORDERS
        )

    is_sqlite = "sqlite" in engine.url.drivername
    metadata = define_schema_metadata(is_sqlite=is_sqlite)

    print("Beginning idempotent batch data load...")
    with engine.begin() as conn:
        # Clear existing data in reverse dependency order
        for table_name in ["payments", "order_items", "orders", "stores", "products", "customers"]:
            conn.execute(text(f"DELETE FROM {table_name}"))

        # Batch insert customers
        print(f"Loading {len(dataset['customers'])} customers...")
        conn.execute(metadata.tables["customers"].insert(), dataset["customers"])

        # Batch insert products
        print(f"Loading {len(dataset['products'])} products...")
        conn.execute(metadata.tables["products"].insert(), dataset["products"])

        # Batch insert stores
        print(f"Loading {len(dataset['stores'])} stores...")
        conn.execute(metadata.tables["stores"].insert(), dataset["stores"])

        # Batch insert orders (chunked into batches of 1000 for efficiency)
        print(f"Loading {len(dataset['orders'])} orders...")
        chunk_size = 1000
        for i in range(0, len(dataset["orders"]), chunk_size):
            chunk = dataset["orders"][i:i + chunk_size]
            conn.execute(metadata.tables["orders"].insert(), chunk)

        # Batch insert order_items (chunked)
        print(f"Loading {len(dataset['order_items'])} order items...")
        for i in range(0, len(dataset["order_items"]), chunk_size):
            chunk = dataset["order_items"][i:i + chunk_size]
            conn.execute(metadata.tables["order_items"].insert(), chunk)

        # Batch insert payments (chunked)
        print(f"Loading {len(dataset['payments'])} payments...")
        for i in range(0, len(dataset["payments"]), chunk_size):
            chunk = dataset["payments"][i:i + chunk_size]
            conn.execute(metadata.tables["payments"].insert(), chunk)

        # For PostgreSQL, synchronize primary key auto-increment sequences
        if "postgresql" in engine.url.drivername:
            print("Synchronizing PostgreSQL sequences...")
            for table, col in [
                ("customers", "customer_id"),
                ("products", "product_id"),
                ("stores", "store_id"),
                ("orders", "order_id"),
                ("order_items", "item_id"),
                ("payments", "payment_id"),
            ]:
                conn.execute(text(f"SELECT setval('{table}_{col}_seq', (SELECT MAX({col}) FROM {table}))"))

    print("Data loading completed successfully!")


def main():
    parser = argparse.ArgumentParser(description="Agentic AI Data Analyst - Database Loader")
    parser.add_argument("--init-schema", action="store_true", help="Drop and recreate database schema")
    parser.add_argument("--seed", action="store_true", help="Seed database with synthetic dataset")
    parser.add_argument("--reset", action="store_true", help="Recreate schema and seed dataset")
    parser.add_argument("--db-url", type=str, default=None, help="Custom SQLAlchemy database connection URL")
    args = parser.parse_args()

    engine = get_engine(args.db_url)

    if args.reset:
        init_schema(engine)
        seed_data(engine)
    elif args.init_schema:
        init_schema(engine)
    elif args.seed:
        seed_data(engine)
    else:
        print("No action specified. Use --reset, --init-schema, or --seed. Run with --help for options.")


if __name__ == "__main__":
    main()
