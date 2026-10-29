"""
app/agent/nodes/validate_sql.py
-------------------------------
Node 4: Multi-layer AST security validation using SQLGlot.
Enforces single-statement SELECT guarantees, table whitelists,
column checking, and automatic LIMIT 100 injection.
"""

from app.agent.state import AgentState
from app.agent.validator import validator


def validate_sql(state: AgentState) -> AgentState:
    """Validates the generated SQL query using the AST security engine."""
    step_count = state.get("step_count", 0) + 1
    generated_sql = state.get("generated_sql") or ""
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 2)

    val_result = validator.validate(generated_sql)

    if val_result["is_valid"]:
        return {
            **state,
            "step_count": step_count,
            "generated_sql": val_result["sanitized_sql"],
            "validation_result": val_result,
            "error_details": None,
            "workflow_status": "in_progress"
        }
    else:
        new_retry_count = retry_count + 1
        is_exhausted = new_retry_count > max_retries

        return {
            **state,
            "step_count": step_count,
            "validation_result": val_result,
            "retry_count": new_retry_count,
            "error_details": val_result["error"],
            "workflow_status": "failed" if is_exhausted else "in_progress"
        }
