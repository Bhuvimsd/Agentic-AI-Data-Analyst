"""
tests/test_database.py
----------------------
Unit and integration tests for the database connection layer:
- Successful database connection and health ping
- Graceful database unavailable error handling
- Pydantic Settings configuration validation
- Resource cleanup and connection release back to the pool
- Statement timeout configuration
- Separation of administrative and read-only credentials
"""

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from app.config import Settings, settings
from app.database import (
    check_database_health, 
    get_readonly_connection, 
    set_statement_timeout
)


def test_successful_database_connection(test_engine):
    """Verifies that health check passes and measures latency on a live engine."""
    health = check_database_health(test_engine)
    assert health["status"] == "healthy"
    assert health["connected"] is True
    assert health["latency_ms"] >= 0
    assert health["dialect"] in ("sqlite", "postgresql")
    assert health["error"] is None


def test_database_unavailable_handling():
    """
    Verifies that an unreachable database returns status='unhealthy'
    with safe sanitized error reporting without raising an unhandled exception.
    """
    from unittest.mock import MagicMock
    mock_engine = MagicMock()
    mock_engine.connect.side_effect = Exception("Connection to database server refused (timeout)")
    mock_engine.dialect.name = "postgresql"

    health = check_database_health(mock_engine)
    assert health["status"] == "unhealthy"
    assert health["connected"] is False
    assert health["error"] is not None
    assert "Database service is unreachable" in health["error"]


def test_invalid_configuration():
    """Verifies that invalid environment configurations trigger Pydantic validation errors."""
    # Test invalid port
    with pytest.raises(ValidationError) as exc_info:
        Settings(DB_PORT=99999)
    assert "DB_PORT must be between 1 and 65535" in str(exc_info.value)

    # Test invalid timeout
    with pytest.raises(ValidationError) as exc_info:
        Settings(QUERY_TIMEOUT_SECONDS=0)
    assert "QUERY_TIMEOUT_SECONDS must be between 1 and 120" in str(exc_info.value)

    # Test negative limit
    with pytest.raises(ValidationError) as exc_info:
        Settings(MAX_ROW_LIMIT=0)
    assert "MAX_ROW_LIMIT must be >= 1" in str(exc_info.value)


def test_resource_cleanup(test_engine):
    """
    Verifies that the dependency injection generator closes connections
    and returns them to the pool after context exit.
    """
    gen = get_readonly_connection()
    conn = next(gen)
    
    # Assert connection is active during request processing
    assert conn is not None
    assert not conn.closed
    res = conn.execute(text("SELECT 1")).scalar()
    assert res == 1

    # Simulate request lifecycle completion (finally block of generator)
    try:
        next(gen)
    except StopIteration:
        pass

    # Assert connection is closed / returned to pool
    assert conn.closed, "Connection was not closed after generator completion"


def test_statement_timeout_setting(test_engine):
    """Verifies statement timeout application does not crash on any dialect."""
    with test_engine.connect() as conn:
        set_statement_timeout(conn, timeout_seconds=5)
        # Verify connection remains functional
        res = conn.execute(text("SELECT 1")).scalar()
        assert res == 1


def test_separate_credentials_configuration():
    """Verifies that admin and read-only connection strings are configured separately."""
    assert settings.DATABASE_URL is not None
    assert settings.DATABASE_URL_READONLY is not None
    # Verify read-only role user is different from admin user in default config
    assert "analyst_readonly" in settings.DATABASE_URL_READONLY or settings.DATABASE_URL != settings.DATABASE_URL_READONLY
