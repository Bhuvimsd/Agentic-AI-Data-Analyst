"""
app/agent/nodes/understand_question.py
--------------------------------------
Node 1: Interprets business intent, checks for prompt injections,
and catches missing/ambiguous entities before query generation.
"""

import re
from app.agent.state import AgentState

INJECTION_PATTERNS = [
    r"\bDROP\s+TABLE\b",
    r"\bTRUNCATE\b",
    r"\bDELETE\s+FROM\b",
    r"\bUPDATE\s+\w+\s+SET\b",
    r"\bALTER\s+TABLE\b",
    r"\bCREATE\s+(TABLE|USER|ROLE)\b",
    r"\bGRANT\s+\w+\b",
    r"\bREVOKE\s+\w+\b",
    r"\bINSERT\s+INTO\b",
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"disregard\s+(all\s+)?prior\s+instructions"
]

AMBIGUOUS_MISSING_ENTITIES = [
    ("profit", "The analytical database tracks prices and revenues, but does not contain cost or profit margin figures."),
    ("margin", "Profit margins cannot be computed without cost data. You can view total sales revenue instead."),
    ("cost", "Product manufacturing or acquisition cost is not stored in our catalog."),
    ("churn", "Customer churn rate is not pre-computed. You can analyze repeat orders or customer ordering frequency instead."),
    ("salary", "Employee and payroll data is outside the scope of this e-commerce analytics database."),
    ("email", "Customer email addresses are omitted for privacy. You can query customers by name or city instead.")
]


def understand_question(state: AgentState) -> AgentState:
    """Classifies user intent, defends against prompt injections, and flags ambiguous inquiries."""
    question = (state.get("question") or "").strip()
    step_count = state.get("step_count", 0) + 1
    
    # Empty question
    if not question:
        return {
            **state,
            "step_count": step_count,
            "intent": "ambiguous",
            "workflow_status": "needs_clarification",
            "clarification_message": "Please enter a specific business or analytical question.",
            "error_details": "Empty inquiry received."
        }

    # Prompt injection check
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, question, re.IGNORECASE):
            return {
                **state,
                "step_count": step_count,
                "intent": "unsafe_injection",
                "workflow_status": "rejected",
                "rejection_reason": "Destructive SQL commands (DROP, TRUNCATE, DELETE, UPDATE, ALTER) are strictly prohibited.",
                "error_details": "Prompt injection / mutation attempt detected."
            }

    # Missing entity check
    q_lower = question.lower()
    for term, reason in AMBIGUOUS_MISSING_ENTITIES:
        if re.search(rf"\b{term}\b", q_lower):
            return {
                **state,
                "step_count": step_count,
                "intent": "ambiguous",
                "workflow_status": "needs_clarification",
                "clarification_message": reason,
                "error_details": f"Inquiry refers to missing entity '{term}'."
            }

    # Standard analytical intent
    return {
        **state,
        "step_count": step_count,
        "intent": "analytical_query",
        "workflow_status": "in_progress",
        "retry_count": state.get("retry_count", 0),
        "max_retries": 2
    }
