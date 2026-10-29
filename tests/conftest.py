"""
tests/conftest.py
-----------------
Pytest configuration and shared fixtures for test isolation across Phase 1 & Phase 2.
"""

import os
import sys
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings
from app.main import app
import app.database as app_db
from scripts.load_data import init_schema, seed_data
from scripts.generate_data import generate_synthetic_dataset

TEST_DB_FILE = PROJECT_ROOT / "test_temp_conftest.db"
TEST_DB_URL = f"sqlite:///{TEST_DB_FILE}"


@pytest.fixture(scope="session")
def test_engine():
    """
    Session-scoped test database engine initialized with Phase 1 schema and seeded data.
    """
    engine = create_engine(TEST_DB_URL, echo=False)
    
    # Register to_char function on SQLite connection for PostgreSQL query compatibility
    from sqlalchemy import event
    @event.listens_for(engine, "connect")
    def register_sqlite_functions(dbapi_conn, connection_record):
        try:
            dbapi_conn.create_function("to_char", 2, lambda d, fmt: str(d)[:7] if d else None)
        except Exception:
            pass

    # Initialize schema and seed data
    init_schema(engine)
    dataset = generate_synthetic_dataset(num_customers=500, num_orders=2200, seed=42)
    seed_data(engine, dataset=dataset)
    
    # Override app engines with the test engine
    orig_readonly = app_db.readonly_engine
    orig_admin = app_db.admin_engine
    app_db.readonly_engine = engine
    app_db.admin_engine = engine
    
    yield engine
    
    # Restore original engines
    app_db.readonly_engine = orig_readonly
    app_db.admin_engine = orig_admin
    engine.dispose()
    
    if TEST_DB_FILE.exists():
        try:
            TEST_DB_FILE.unlink()
        except Exception:
            pass


@pytest.fixture(scope="session")
def client(test_engine):
    """
    FastAPI TestClient fixture configured with initialized test database.
    """
    with TestClient(app) as test_client:
        yield test_client
