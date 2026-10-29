"""
app/api/schemas.py
------------------
Pydantic v2 data models for API requests, responses, schema metadata, and query validation.
"""

from enum import Enum
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


# ------------------------------------------------------------------------------
# 1. Health & Status Schemas
# ------------------------------------------------------------------------------
class HealthResponse(BaseModel):
    """System health and database connectivity response."""
    status: str = Field(..., description="'healthy' or 'unhealthy'")
    database_connected: bool = Field(..., description="True if database responds to ping")
    database_latency_ms: float = Field(..., description="Ping latency in milliseconds")
    dialect: str = Field(..., description="Database engine dialect (e.g. postgresql, sqlite)")
    timestamp: str = Field(..., description="ISO 8601 server timestamp")
    version: str = Field(..., description="API service version")
    error: Optional[str] = Field(default=None, description="Error message if unhealthy")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "status": "healthy",
            "database_connected": True,
            "database_latency_ms": 2.45,
            "dialect": "postgresql",
            "timestamp": "2026-10-29T13:30:00Z",
            "version": "0.2.0",
            "error": None
        }
    })


# ------------------------------------------------------------------------------
# 2. Database Schema Inspection Schemas
# ------------------------------------------------------------------------------
class ColumnMetadata(BaseModel):
    """Metadata describing a single table column."""
    column_name: str
    data_type: str
    is_nullable: bool
    is_primary_key: bool
    is_foreign_key: bool
    foreign_key_target: Optional[str] = None


class TableMetadata(BaseModel):
    """Metadata describing an analytical table."""
    table_name: str
    row_count: int
    columns: List[ColumnMetadata]


class SchemaResponse(BaseModel):
    """Complete analytical database schema catalog."""
    status: str = "success"
    database_name: str
    total_tables: int
    tables: List[TableMetadata]


# ------------------------------------------------------------------------------
# 3. Analytical Query Request & Response Schemas
# ------------------------------------------------------------------------------
class PredefinedQueryID(str, Enum):
    """Whitelisted predefined analytical query identifiers."""
    TOTAL_REVENUE = "TOTAL_REVENUE"
    TOP_PRODUCTS_BY_REVENUE = "TOP_PRODUCTS_BY_REVENUE"
    MONTHLY_REVENUE = "MONTHLY_REVENUE"
    TOP_CUSTOMERS_BY_SPEND = "TOP_CUSTOMERS_BY_SPEND"
    REVENUE_BY_REGION = "REVENUE_BY_REGION"
    AVERAGE_ORDER_VALUE = "AVERAGE_ORDER_VALUE"
    PRODUCTS_NEVER_ORDERED = "PRODUCTS_NEVER_ORDERED"
    REPEAT_CUSTOMERS = "REPEAT_CUSTOMERS"
    PAYMENT_ANOMALIES = "PAYMENT_ANOMALIES"
    CATEGORY_SALES = "CATEGORY_SALES"


class QueryParameters(BaseModel):
    """Optional, strictly validated analytical query parameters."""
    limit: Optional[int] = Field(
        default=None, 
        ge=1, 
        le=1000, 
        description="Row limit (between 1 and 1000)"
    )
    region: Optional[str] = Field(
        default=None, 
        pattern="^(North|South|East|West|Central)$",
        description="Filter by geographic commercial region"
    )
    category: Optional[str] = Field(
        default=None,
        description="Filter by product category"
    )
    start_date: Optional[str] = Field(
        default=None, 
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Filter by start date (YYYY-MM-DD)"
    )
    end_date: Optional[str] = Field(
        default=None, 
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Filter by end date (YYYY-MM-DD)"
    )


class AnalyticsQueryRequest(BaseModel):
    """Controlled analytical query invocation request."""
    query_id: PredefinedQueryID = Field(
        ..., 
        description="Approved analytical query ID to execute"
    )
    parameters: QueryParameters = Field(
        default_factory=QueryParameters,
        description="Validated parameters for the query"
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "query_id": "TOP_PRODUCTS_BY_REVENUE",
            "parameters": {
                "limit": 5,
                "category": "Electronics"
            }
        }
    })


class QueryExecutionMetadata(BaseModel):
    """Telemetry and execution metrics for an executed query."""
    query_id: str
    execution_time_ms: float
    row_count: int
    applied_limit: int
    statement_timeout_seconds: int


class AnalyticsQueryResponse(BaseModel):
    """Structured analytical response with data and execution metadata."""
    success: bool
    query_id: str
    title: str
    description: str
    metadata: QueryExecutionMetadata
    columns: List[str]
    data: List[Dict[str, Any]]
    error: Optional[str] = None


class SafeErrorResponse(BaseModel):
    """Sanitized, safe error message payload."""
    error: str
    details: Optional[Any] = None
    timestamp: str
