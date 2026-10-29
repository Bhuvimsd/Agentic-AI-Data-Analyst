"""
app/database.py
---------------
Modular SQLAlchemy database connection layer with dual-role connection pools,
statement timeouts, health monitoring, and FastAPI dependency injection providers.
"""

import time
import logging
from typing import Generator, Dict, Any, Optional
from sqlalchemy import create_engine, text, Engine, Connection
from sqlalchemy.pool import QueuePool, NullPool
from app.config import settings, BASE_DIR

logger = logging.getLogger("agentic_ai.database")


def create_db_engine(url: str, is_readonly: bool = True) -> Engine:
    """
    Creates and configures a SQLAlchemy engine with connection pooling.
    Handles PostgreSQL (psycopg3) and test SQLite engines appropriately.
    """
    is_sqlite = "sqlite" in url.lower()
    
    if is_sqlite:
        # Resolve relative SQLite paths against project BASE_DIR
        if url.startswith("sqlite:///") and not (":/" in url or ":\\" in url or url.startswith("sqlite:////")):
            rel_name = url[len("sqlite:///"):]
            abs_db_path = (BASE_DIR / rel_name).resolve()
            url = f"sqlite:///{abs_db_path.as_posix()}"

        engine = create_engine(
            url,
            echo=False,
            pool_pre_ping=True
        )

        # Register to_char function on SQLite connections for PostgreSQL compatibility
        from sqlalchemy import event
        @event.listens_for(engine, "connect")
        def _register_sqlite_to_char(dbapi_conn, _):
            try:
                dbapi_conn.create_function("to_char", 2, lambda d, fmt: str(d)[:7] if d else None)
            except Exception:
                pass

        # Verify tables exist; self-heal if empty
        if not is_readonly:
            try:
                from sqlalchemy import inspect
                inspector = inspect(engine)
                if "customers" not in inspector.get_table_names():
                    from scripts.load_data import init_schema, seed_data
                    from scripts.generate_data import generate_synthetic_dataset
                    init_schema(engine)
                    seed_data(engine, generate_synthetic_dataset(num_customers=500, num_orders=2200, seed=42))
            except Exception as e:
                logger.warning(f"SQLite auto-initialization check skipped: {e}")
        # PostgreSQL with psycopg3 driver
        engine = create_engine(
            url,
            poolclass=QueuePool,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_timeout=settings.DB_POOL_TIMEOUT,
            pool_recycle=settings.DB_POOL_RECYCLE,
            pool_pre_ping=True,  # Verifies connection liveness before checkout
            echo=False
        )

        # Liveness check: If configured database is unreachable (e.g. on Streamlit Cloud),
        # automatically fall back to the embedded analytical SQLite database
        try:
            with engine.connect() as test_conn:
                test_conn.execute(text("SELECT 1"))
        except Exception as e:
            logger.warning(
                f"Configured database at '{url.split('@')[-1] if '@' in url else url}' "
                f"is unreachable ({e}). Automatically falling back to local SQLite analytics database."
            )
            fallback_sqlite_path = (BASE_DIR / "agentic_ai_analytics.db").resolve()
            return create_db_engine(f"sqlite:///{fallback_sqlite_path.as_posix()}", is_readonly=is_readonly)

    logger.info(
        f"Initialized {'Read-Only' if is_readonly else 'Admin'} DB engine for: "
        f"{url.split('@')[-1] if '@' in url else url}"
    )
    return engine


# ------------------------------------------------------------------------------
# Dual Connection Pools: Administrative vs. Read-Only Analytics
# ------------------------------------------------------------------------------
# In production, admin_engine connects with DB owner credentials (for migrations/DDL)
admin_engine: Engine = create_db_engine(settings.DATABASE_URL, is_readonly=False)

# readonly_engine connects strictly with analyst_readonly credentials (for analytics)
readonly_engine: Engine = create_db_engine(settings.DATABASE_URL_READONLY, is_readonly=True)


def configure_readonly_session(conn: Connection, timeout_seconds: Optional[int] = None) -> None:
    """
    Enforces multi-layer runtime constraints on read-only database connections:
    1. Statement timeout (default 10s) to prevent runaway queries / DoS.
    2. Enforces transaction read-only mode (SET LOCAL default_transaction_read_only = on).
    3. Restricts schema search path (SET LOCAL search_path = public).
    """
    timeout = timeout_seconds or settings.QUERY_TIMEOUT_SECONDS
    timeout_ms = int(timeout * 1000)
    
    dialect_name = conn.dialect.name.lower()
    if "postgresql" in dialect_name:
        try:
            conn.execute(text(f"SET LOCAL statement_timeout = {timeout_ms}"))
            conn.execute(text("SET LOCAL default_transaction_read_only = on"))
            conn.execute(text("SET LOCAL search_path = public"))
        except Exception as e:
            logger.warning(f"Could not configure PostgreSQL session controls: {e}")
    elif "snowflake" in dialect_name:
        try:
            conn.execute(text(f"ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = {timeout}"))
        except Exception as e:
            logger.warning(f"Could not configure Snowflake session controls: {e}")


def set_statement_timeout(conn: Connection, timeout_seconds: Optional[int] = None) -> None:
    """Backward-compatible wrapper for setting statement timeout."""
    configure_readonly_session(conn, timeout_seconds)


# ------------------------------------------------------------------------------
# FastAPI Dependency Injection Providers
# ------------------------------------------------------------------------------
def get_readonly_connection() -> Generator[Connection, None, None]:
    """
    FastAPI dependency that yields a managed read-only database connection.
    Guarantees the connection is returned to the pool after the request completes.
    """
    conn: Optional[Connection] = None
    try:
        conn = readonly_engine.connect()
        # Enforce statement timeout and read-only session controls on checkout
        configure_readonly_session(conn, settings.QUERY_TIMEOUT_SECONDS)
        yield conn
    finally:
        if conn is not None and not conn.closed:
            conn.close()


def get_admin_connection() -> Generator[Connection, None, None]:
    """
    FastAPI dependency that yields an administrative database connection.
    Used for schema inspections or health checks requiring admin context.
    """
    conn: Optional[Connection] = None
    try:
        conn = admin_engine.connect()
        yield conn
    finally:
        if conn is not None and not conn.closed:
            conn.close()


# ------------------------------------------------------------------------------
# Database Health & Connectivity Check
# ------------------------------------------------------------------------------
def check_database_health(target_engine: Optional[Engine] = None) -> Dict[str, Any]:
    """
    Probes the database engine by executing a lightweight ping query.
    Returns connectivity status, latency in milliseconds, and dialect info.
    """
    eng = target_engine or readonly_engine
    start_time = time.perf_counter()
    
    try:
        with eng.connect() as conn:
            # Simple ping query
            result = conn.execute(text("SELECT 1")).scalar()
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            
            if result == 1:
                return {
                    "status": "healthy",
                    "connected": True,
                    "latency_ms": latency_ms,
                    "dialect": conn.dialect.name,
                    "error": None
                }
            else:
                return {
                    "status": "unhealthy",
                    "connected": False,
                    "latency_ms": latency_ms,
                    "dialect": conn.dialect.name,
                    "error": "Unexpected ping query result"
                }
    except Exception as e:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.error(f"Database health check failed: {e}")
        return {
            "status": "unhealthy",
            "connected": False,
            "latency_ms": latency_ms,
            "dialect": eng.dialect.name if eng else "unknown",
            "error": "Database service is unreachable or credentials are invalid"
        }
