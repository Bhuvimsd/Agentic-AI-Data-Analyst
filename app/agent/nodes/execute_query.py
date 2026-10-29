"""
app/agent/nodes/execute_query.py
--------------------------------
Node 5: Read-only database query execution with statement timeout.
Execution is mathematically gated behind successful validation.
"""

import time
from decimal import Decimal
from datetime import datetime, date
from typing import Any
from sqlalchemy import text
from app.agent.state import AgentState
import app.database as app_db
from app.config import settings


def serialize_val(v: Any) -> Any:
    """Serializes Decimal and dates to JSON-safe primitives."""
    if isinstance(v, Decimal):
        return float(v)
    elif isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def execute_query(state: AgentState, engine=None) -> AgentState:
    """Executes the validated SQL query against the read-only database pool."""
    step_count = state.get("step_count", 0) + 1
    val_result = state.get("validation_result") or {}

    # Strict Security Gate: Never execute without prior validation approval!
    if not val_result.get("is_valid"):
        return {
            **state,
            "step_count": step_count,
            "workflow_status": "failed",
            "error_details": "Execution blocked: Query did not pass AST security validation."
        }

    sql_to_run = state.get("generated_sql") or ""
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 2)
    target_engine = engine or app_db.readonly_engine

    start_time = time.perf_counter()
    try:
        with target_engine.connect() as conn:
            # Enforce query statement timeout
            app_db.set_statement_timeout(conn, settings.QUERY_TIMEOUT_SECONDS)
            if "sqlite" in str(target_engine.url).lower():
                try:
                    raw_db = getattr(conn.connection, "dbapi_connection", conn.connection)
                    raw_db.create_function("to_char", 2, lambda d, fmt: str(d)[:7] if d else None)
                except Exception:
                    pass
            cursor_res = conn.execute(text(sql_to_run))
            columns = list(cursor_res.keys())
            raw_rows = cursor_res.fetchall()

            data = [
                {col: serialize_val(val) for col, val in zip(columns, row)}
                for row in raw_rows
            ]
            execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)

            return {
                **state,
                "step_count": step_count,
                "query_execution_result": data,
                "columns": columns,
                "row_count": len(data),
                "execution_time_ms": execution_time_ms,
                "error_details": None,
                "workflow_status": "in_progress"
            }

    except Exception as e:
        execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
        new_retry_count = retry_count + 1
        is_exhausted = new_retry_count > max_retries

        error_msg = f"Database execution error: {str(e)}"
        return {
            **state,
            "step_count": step_count,
            "execution_time_ms": execution_time_ms,
            "retry_count": new_retry_count,
            "error_details": error_msg,
            "workflow_status": "failed" if is_exhausted else "in_progress"
        }
