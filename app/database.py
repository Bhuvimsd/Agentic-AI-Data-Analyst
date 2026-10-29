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
from app.config import settings

logger = logging.getLogger("agentic_ai.database")


def create_db_engine(url: str, is_readonly: bool = True) -> Engine:
    """
    Creates and configures a SQLAlchemy engine with connection pooling.
    Handles PostgreSQL (psycopg3) and test SQLite engines appropriately.
    """
    is_sqlite = "sqlite" in url.lower()
    
    if is_sqlite:
        # SQLite uses StaticPool or NullPool for testing
        engine = create_engine(
            url,
            echo=False,
            pool_pre_ping=True
        )
    else:
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


def set_statement_timeout(conn: Connection, timeout_seconds: Optional[int] = None) -> None:
    """
    Sets a local statement timeout on the connection to prevent runaway queries.
    PostgreSQL: Executes 'SET LOCAL statement_timeout = ...'
    """
    timeout = timeout_seconds or settings.QUERY_TIMEOUT_SECONDS
    timeout_ms = int(timeout * 1000)
    
    if "postgresql" in conn.dialect.name.lower():
        try:
            conn.execute(text(f"SET LOCAL statement_timeout = {timeout_ms}"))
        except Exception as e:
            logger.warning(f"Could not set statement_timeout on PostgreSQL connection: {e}")


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
        # Enforce statement timeout on checkout
        set_statement_timeout(conn, settings.QUERY_TIMEOUT_SECONDS)
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
