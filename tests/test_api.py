"""
tests/test_api.py
-----------------
API integration tests for FastAPI analytics gateway:
- GET / root endpoint
- GET /health healthy and unhealthy states
- GET /schema dynamic table metadata extraction
- POST /analytics/query for all registered analytical queries
- Rejection of invalid query IDs, invalid parameters, and arbitrary SQL
- Request payload size limiter middleware (HTTP 413)
"""

from unittest.mock import patch
import pytest
from app.config import settings
from app.api.schemas import PredefinedQueryID


def test_root_endpoint(client):
    """Verifies that root endpoint returns service metadata and links to docs."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"
    assert data["documentation"] == "/docs"
    assert "version" in data


def test_health_endpoint_healthy(client):
    """Verifies GET /health returns 200 OK and healthy database status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database_connected"] is True
    assert data["database_latency_ms"] >= 0
    assert data["error"] is None
    assert "dialect" in data
    assert "timestamp" in data


def test_health_endpoint_unhealthy(client):
    """Verifies GET /health returns 503 when the database is unavailable."""
    unhealthy_mock = {
        "status": "unhealthy",
        "connected": False,
        "latency_ms": 15.2,
        "dialect": "postgresql",
        "error": "Connection refused"
    }
    with patch("app.api.routes.check_database_health", return_value=unhealthy_mock):
        response = client.get("/health")
        assert response.status_code == 503
        data = response.json()["detail"]
        assert data["status"] == "unhealthy"
        assert data["database_connected"] is False
        assert "Connection refused" in data["error"]


def test_schema_endpoint(client):
    """Verifies GET /schema inspects and returns metadata for all 6 analytical tables."""
    response = client.get("/schema")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["total_tables"] == 6

    table_names = [t["table_name"] for t in data["tables"]]
    expected_tables = ["customers", "products", "stores", "orders", "order_items", "payments"]
    for expected in expected_tables:
        assert expected in table_names

    # Check order_items column definitions
    order_items_meta = next(t for t in data["tables"] if t["table_name"] == "order_items")
    col_names = [c["column_name"] for c in order_items_meta["columns"]]
    assert "item_id" in col_names
    assert "order_id" in col_names
    assert "unit_price" in col_names
    assert order_items_meta["row_count"] > 0


# ------------------------------------------------------------------------------
# Controlled Analytical Query Execution Tests
# ------------------------------------------------------------------------------
def test_query_total_revenue(client):
    """Verifies POST /analytics/query with TOTAL_REVENUE."""
    payload = {"query_id": "TOTAL_REVENUE"}
    response = client.post("/analytics/query", json=payload)
    assert response.status_code == 200
    res = response.json()
    assert res["success"] is True
    assert res["query_id"] == "TOTAL_REVENUE"
    assert len(res["data"]) == 1
    assert res["data"][0]["total_revenue"] > 1000000
    assert res["metadata"]["row_count"] == 1
    assert res["metadata"]["execution_time_ms"] >= 0


def test_query_top_products_with_parameterized_limit(client):
    """Verifies POST /analytics/query with TOP_PRODUCTS_BY_REVENUE and limit parameter."""
    payload = {
        "query_id": "TOP_PRODUCTS_BY_REVENUE",
        "parameters": {"limit": 3}
    }
    response = client.post("/analytics/query", json=payload)
    assert response.status_code == 200
    res = response.json()
    assert res["success"] is True
    assert len(res["data"]) == 3
    assert res["metadata"]["applied_limit"] == 3
    # Check descending order
    revs = [row["total_revenue"] for row in res["data"]]
    assert revs == sorted(revs, reverse=True)


def test_query_revenue_by_region_with_filter(client):
    """Verifies POST /analytics/query with REVENUE_BY_REGION filtered to 'South'."""
    payload = {
        "query_id": "REVENUE_BY_REGION",
        "parameters": {"region": "South"}
    }
    response = client.post("/analytics/query", json=payload)
    assert response.status_code == 200
    res = response.json()
    assert res["success"] is True
    assert len(res["data"]) == 1
    assert res["data"][0]["region"] == "South"


def test_query_average_order_value(client):
    """Verifies POST /analytics/query with AVERAGE_ORDER_VALUE."""
    payload = {"query_id": "AVERAGE_ORDER_VALUE"}
    response = client.post("/analytics/query", json=payload)
    assert response.status_code == 200
    res = response.json()
    assert res["success"] is True
    assert res["data"][0]["average_order_value"] > 0


def test_query_products_never_ordered(client):
    """Verifies POST /analytics/query identifies unpurchased items."""
    payload = {"query_id": "PRODUCTS_NEVER_ORDERED"}
    response = client.post("/analytics/query", json=payload)
    assert response.status_code == 200
    res = response.json()
    assert res["success"] is True
    assert len(res["data"]) >= 2


def test_query_payment_anomalies(client):
    """Verifies POST /analytics/query detects the 2 deliberate payment anomalies."""
    payload = {"query_id": "PAYMENT_ANOMALIES"}
    response = client.post("/analytics/query", json=payload)
    assert response.status_code == 200
    res = response.json()
    assert res["success"] is True
    assert len(res["data"]) == 2
    order_ids = {row["order_id"] for row in res["data"]}
    assert order_ids == {100, 250}


def test_query_category_sales(client):
    """Verifies POST /analytics/query with CATEGORY_SALES."""
    payload = {"query_id": "CATEGORY_SALES"}
    response = client.post("/analytics/query", json=payload)
    assert response.status_code == 200
    res = response.json()
    assert res["success"] is True
    assert len(res["data"]) >= 5


# ------------------------------------------------------------------------------
# Input Validation & Security Rejection Tests
# ------------------------------------------------------------------------------
def test_reject_unregistered_query_id(client):
    """Verifies that unapproved query IDs are rejected with 422 Unprocessable Entity."""
    payload = {"query_id": "DROP_DATABASE_CASCADE"}
    response = client.post("/analytics/query", json=payload)
    assert response.status_code == 422
    errors = response.json()["detail"]
    assert any("query_id" in err["loc"] for err in errors)


def test_reject_arbitrary_sql_injection_attempt(client):
    """Verifies that arbitrary SQL text cannot be executed through the endpoint."""
    payload = {
        "query_id": "SELECT * FROM customers; --"
    }
    response = client.post("/analytics/query", json=payload)
    assert response.status_code == 422


def test_reject_invalid_parameter_bounds(client):
    """Verifies that negative limit or excessive limit triggers 422 validation error."""
    # Negative limit
    res1 = client.post("/analytics/query", json={"query_id": "TOTAL_REVENUE", "parameters": {"limit": -5}})
    assert res1.status_code == 422

    # Excessive limit (> 1000)
    res2 = client.post("/analytics/query", json={"query_id": "TOTAL_REVENUE", "parameters": {"limit": 50000}})
    assert res2.status_code == 422

    # Invalid region
    res3 = client.post("/analytics/query", json={"query_id": "REVENUE_BY_REGION", "parameters": {"region": "Antarctica"}})
    assert res3.status_code == 422


def test_request_size_limit_middleware(client):
    """Verifies that requests exceeding the byte limit are rejected with HTTP 413."""
    # Create payload exceeding 1MB
    huge_data = "x" * (settings.MAX_REQUEST_BODY_BYTES + 1024)
    response = client.post(
        "/analytics/query",
        content=huge_data,
        headers={"Content-Length": str(len(huge_data)), "Content-Type": "application/json"}
    )
    assert response.status_code == 413
    assert "Request payload too large" in response.json()["error"]
