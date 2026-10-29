"""
app/agent/nodes/generate_sql.py
-------------------------------
Node 3: Synthesizes a PostgreSQL SELECT query using schema grounding.
Supports self-correction reflection when retrying after a validation or execution error.
"""

from app.agent.state import AgentState
from app.llm.sql_generator import SQLGenerator
from app.llm.client import get_llm_client


def generate_sql(state: AgentState, client=None) -> AgentState:
    """Generates a PostgreSQL query from the question, incorporating error feedback on retries."""
    step_count = state.get("step_count", 0) + 1
    question = state.get("question", "")
    retry_count = state.get("retry_count", 0)
    error_details = state.get("error_details")

    # On retry, augment the question with self-correction guidance
    if retry_count > 0 and error_details:
        augmented_prompt = (
            f"{question}\n\n"
            f"[SELF-CORRECTION NOTE: Your previous attempt failed with error: '{error_details}'. "
            f"Fix this mistake. Ensure only valid columns from allowed tables are used and only SELECT is produced.]"
        )
    else:
        augmented_prompt = question

    generator = SQLGenerator(client=client or get_llm_client())

    try:
        gen_result = generator.generate(augmented_prompt)
        
        if not gen_result.is_safe_query:
            return {
                **state,
                "step_count": step_count,
                "workflow_status": "rejected",
                "rejection_reason": gen_result.rejection_reason or "Query violates security policies.",
                "error_details": gen_result.rejection_reason
            }

        if gen_result.needs_clarification:
            return {
                **state,
                "step_count": step_count,
                "workflow_status": "needs_clarification",
                "clarification_message": gen_result.clarification_message,
                "error_details": "Inquiry is ambiguous or asks for non-existent attributes."
            }

        return {
            **state,
            "step_count": step_count,
            "generated_sql": gen_result.sql,
            "assumptions": gen_result.assumptions,
            "workflow_status": "in_progress"
        }

    except Exception as e:
        return {
            **state,
            "step_count": step_count,
            "workflow_status": "failed",
            "error_details": f"SQL synthesis failed: {str(e)}"
        }
