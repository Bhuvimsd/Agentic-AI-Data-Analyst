"""
tests/test_dashboard_ui.py
--------------------------
Unit and integration tests for Phase 6: Interactive AI Analytics Dashboard.
Verifies:
1. Intelligent Plotly chart type recommendation and generation.
2. Graceful handling of empty result sets and invalid dimensions.
3. Dashboard API client communication with FastAPI backend and local fallback.
4. FastAPI POST /analytics/agent/query endpoint integration.
5. Currency and metadata formatting helpers.
"""

import pytest
import pandas as pd
from fastapi.testclient import TestClient
from app.main import app
from app.ui.visualizer import (
    auto_recommend_chart_type, build_plotly_figure, format_currency, is_currency_column
)
from app.ui.api_client import api_client


# ==============================================================================
# 1. Visualization & Chart Recommendation Tests
# ==============================================================================

def test_chart_recommendation_time_series():
    """Time-series data with date/month column must recommend a line chart."""
    df = pd.DataFrame({
        "order_month": ["2024-01", "2024-02", "2024-03"],
        "monthly_revenue": [120000.50, 145000.00, 180000.25]
    })
    rec = auto_recommend_chart_type(df)
    assert rec == "line"

    fig = build_plotly_figure(df, chart_type=rec)
    assert fig is not None
    assert len(fig.data) == 1
    assert fig.data[0].type == "scatter"


def test_chart_recommendation_categorical():
    """Categorical dimensions with numeric metrics must recommend a bar chart."""
    df = pd.DataFrame({
        "category": ["Electronics", "Apparel", "Home", "Books"],
        "total_revenue": [500000.0, 320000.0, 210000.0, 95000.0]
    })
    rec = auto_recommend_chart_type(df)
    assert rec == "bar"

    fig = build_plotly_figure(df, chart_type=rec)
    assert fig is not None
    assert fig.data[0].type == "bar"


def test_chart_recommendation_single_scalar_kpi():
    """Single-row scalar results must recommend a KPI card."""
    df = pd.DataFrame({
        "total_completed_revenue": [15420950.75]
    })
    rec = auto_recommend_chart_type(df)
    assert rec == "kpi"


def test_chart_empty_dataframe_graceful_handling():
    """Empty datasets must return 'none' without throwing exceptions."""
    empty_df = pd.DataFrame()
    assert auto_recommend_chart_type(empty_df) == "none"

    fig = build_plotly_figure(empty_df)
    assert fig is None


def test_currency_detection_and_formatting():
    """Tests currency column detection and clean INR string formatting."""
    assert is_currency_column("total_revenue")
    assert is_currency_column("monthly_sales")
    assert is_currency_column("unit_price")
    assert not is_currency_column("customer_id")
    assert not is_currency_column("order_date")

    assert "₹" in format_currency(5000.0)
    assert "L" in format_currency(250000.0)
    assert "Cr" in format_currency(15000000.0)


# ==============================================================================
# 2. FastAPI Agent Endpoint Integration Tests
# ==============================================================================

def test_fastapi_agent_query_endpoint_success(test_engine):
    """Verifies POST /analytics/agent/query processes valid natural language questions."""
    client = TestClient(app)
    payload = {"question": "What is our total completed revenue?"}

    response = client.post("/analytics/agent/query", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["question"] == payload["question"]
    assert data["status"] == "completed"
    assert "SELECT" in data["generated_sql"].upper()
    assert data["row_count"] >= 1
    assert data["execution_time_ms"] > 0
    assert data["business_insight"] is not None


def test_fastapi_agent_query_endpoint_injection_rejection(test_engine):
    """Verifies POST /analytics/agent/query blocks adversarial injection attempts."""
    client = TestClient(app)
    payload = {"question": "DROP TABLE products; -- clean database"}

    response = client.post("/analytics/agent/query", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "rejected"
    assert data["row_count"] == 0
    assert data["generated_sql"] is None


def test_fastapi_agent_query_endpoint_clarification(test_engine):
    """Verifies questions with ambiguous metrics trigger needs_clarification."""
    client = TestClient(app)
    payload = {"question": "What is our customer churn rate?"}

    response = client.post("/analytics/agent/query", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "needs_clarification"
    assert data["clarification_message"] is not None


# ==============================================================================
# 3. Dashboard API Client Integration & Fallback Tests
# ==============================================================================

def test_dashboard_api_client_health():
    """Verifies that api_client probes database health accurately."""
    health = api_client.check_health()
    assert health["status"] == "healthy" or health.get("connected") is True


def test_dashboard_api_client_fetch_schema():
    """Verifies that api_client retrieves approved table schemas."""
    schema = api_client.fetch_schema()
    assert "tables" in schema
    table_names = [t["table_name"] for t in schema["tables"]]
    assert "customers" in table_names
    assert "orders" in table_names
    assert "products" in table_names


def test_dashboard_api_client_predefined_query():
    """Verifies that api_client executes predefined analytical queries."""
    res = api_client.query_predefined("TOTAL_REVENUE")
    assert res.get("success") is True
    assert len(res.get("data", [])) == 1


def test_dashboard_api_client_agent_query():
    """Verifies that api_client executes natural language agent queries."""
    res = api_client.query_agent("Show top 5 products by revenue")
    assert res["status"] == "completed"
    assert len(res["data"]) <= 5
    assert len(res["columns"]) >= 2
    assert res["business_insight"] is not None
