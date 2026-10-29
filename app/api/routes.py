"""
app/api/routes.py
-----------------
FastAPI router providing the analytical gateway API:
- GET  /health          : Probe database connectivity and system status
- GET  /schema          : Retrieve analytical table catalog and column definitions
- POST /analytics/query : Execute controlled, approved analytical queries
"""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import Connection
from app.config import settings
import app.database as app_db
from app.database import get_readonly_connection, check_database_health
from app.api.schemas import (
    HealthResponse, SchemaResponse, AnalyticsQueryRequest, 
    AnalyticsQueryResponse, SafeErrorResponse,
    AgentQueryRequest, AgentQueryResponse
)
from app.services.analytics_service import execute_predefined_query, get_database_schema
from app.agent.workflow import run_agentic_workflow

router = APIRouter(tags=["Analytics Gateway"])


# ------------------------------------------------------------------------------
# 1. Health Probe Endpoint
# ------------------------------------------------------------------------------
@router.get(
    "/health",
    response_model=HealthResponse,
    summary="System Health & Database Connectivity Probe",
    description="Validates that the service is running and the database connection pool is responsive."
)
def health_check():
    """Checks database liveness and measures ping latency."""
    health_data = check_database_health()
    now_iso = datetime.now(timezone.utc).isoformat()

    response = HealthResponse(
        status=health_data["status"],
        database_connected=health_data["connected"],
        database_latency_ms=health_data["latency_ms"],
        dialect=health_data["dialect"],
        timestamp=now_iso,
        version=settings.APP_VERSION,
        error=health_data.get("error")
    )

    if not health_data["connected"]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=response.model_dump()
        )

    return response


# ------------------------------------------------------------------------------
# 2. Database Schema Catalog Endpoint
# ------------------------------------------------------------------------------
@router.get(
    "/schema",
    response_model=SchemaResponse,
    summary="Get Approved Analytical Schema Metadata",
    description="Extracts table names, columns, data types, primary keys, and foreign keys for allowed analytical tables."
)
def get_schema(
    conn: Connection = Depends(get_readonly_connection)
):
    """Returns metadata for the analytical tables available to the AI agent."""
    try:
        return get_database_schema(conn)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve database schema metadata."
        )


# ------------------------------------------------------------------------------
# 3. Controlled Analytical Query Endpoint
# ------------------------------------------------------------------------------
@router.post(
    "/analytics/query",
    response_model=AnalyticsQueryResponse,
    responses={
        400: {"model": SafeErrorResponse, "description": "Invalid query parameter"},
        500: {"model": SafeErrorResponse, "description": "Database execution error"}
    },
    summary="Execute Controlled Analytical Query",
    description="Executes a pre-approved, parameterized analytical query using strict read-only connection."
)
def run_analytics_query(
    request: AnalyticsQueryRequest,
    conn: Connection = Depends(get_readonly_connection)
):
    """
    Executes an approved analytical query from the registry with bounded parameters.
    Arbitrary, unvalidated SQL is strictly forbidden from execution.
    """
    try:
        response = execute_predefined_query(
            conn=conn,
            query_id=request.query_id,
            params=request.parameters
        )
        return response
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="A database error occurred while processing the analytical query."
        )


# ------------------------------------------------------------------------------
# 4. Agentic AI Natural Language Query Endpoint
# ------------------------------------------------------------------------------
@router.post(
    "/analytics/agent/query",
    response_model=AgentQueryResponse,
    responses={
        400: {"model": SafeErrorResponse, "description": "Invalid input"},
        500: {"model": SafeErrorResponse, "description": "Workflow execution error"}
    },
    summary="Agentic AI Natural Language Query",
    description="Processes a natural-language business question through the stateful LangGraph agentic workflow with AST security guarantees."
)
def run_agent_query(
    request: AgentQueryRequest
):
    """
    Executes the end-to-end LangGraph agent workflow:
    1. Interprets question
    2. Retrieves approved schema
    3. Generates PostgreSQL SELECT query
    4. Validates SQL AST with SQLGuard
    5. Executes approved query with read-only credentials
    6. Analyzes results and generates grounded explanation
    """
    try:
        final_state = run_agentic_workflow(
            question=request.question,
            engine=app_db.readonly_engine
        )
        now_iso = datetime.now(timezone.utc).isoformat()
        
        rows = final_state.get("query_execution_result") or []
        cols = final_state.get("columns") or (list(rows[0].keys()) if rows else [])
        
        return AgentQueryResponse(
            question=request.question,
            status=final_state.get("workflow_status", "failed"),
            generated_sql=final_state.get("generated_sql"),
            columns=cols,
            data=rows,
            row_count=final_state.get("row_count", len(rows)),
            execution_time_ms=final_state.get("execution_time_ms", 0.0),
            business_insight=final_state.get("business_insight"),
            clarification_message=final_state.get("clarification_message"),
            error_details=final_state.get("error_details"),
            retry_count=final_state.get("retry_count", 0),
            timestamp=now_iso
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent workflow error: {str(e)}"
        )

