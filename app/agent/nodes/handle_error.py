"""
app/agent/nodes/handle_error.py
------------------------------
Node 8: Handles workflow errors, prompt rejections, and clarification requests.
Produces safe, structured user explanations and prevents unhandled crashes.
"""

from app.agent.state import AgentState


def handle_error(state: AgentState) -> AgentState:
    """Formats safe, actionable error or clarification responses for terminal states."""
    step_count = state.get("step_count", 0) + 1
    status = state.get("workflow_status", "failed")
    error_details = state.get("error_details")
    rejection = state.get("rejection_reason")
    clarification = state.get("clarification_message")

    if status == "rejected":
        explanation = f"Security Policy Violation: {rejection or 'The requested query contains unauthorized operations.'}"
    elif status == "needs_clarification":
        explanation = f"Clarification Required: {clarification or 'The inquiry is ambiguous or references non-existent columns.'}"
    else:
        explanation = f"Workflow Execution Failed: {error_details or 'The query could not be completed after validation and retries.'}"

    return {
        **state,
        "step_count": step_count,
        "business_insight": explanation,
        "workflow_status": status
    }
