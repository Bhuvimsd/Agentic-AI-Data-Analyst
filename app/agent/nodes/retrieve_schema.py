"""
app/agent/nodes/retrieve_schema.py
----------------------------------
Node 2: Retrieves allowed analytical tables, schema definitions,
and business accounting rules to ground SQL generation.
"""

from app.agent.state import AgentState
from app.llm.schema_context import get_analytical_schema_prompt_context, ALLOWED_TABLES


def retrieve_schema(state: AgentState) -> AgentState:
    """Retrieves grounded analytical schema metadata and business definitions."""
    step_count = state.get("step_count", 0) + 1
    schema_prompt = get_analytical_schema_prompt_context()

    return {
        **state,
        "step_count": step_count,
        "relevant_schema": schema_prompt,
        "allowed_tables": ALLOWED_TABLES
    }
