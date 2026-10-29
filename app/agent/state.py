"""
app/agent/state.py
------------------
Typed LangGraph Agent State definition for Agentic AI Data Analyst.
Tracks execution lifecycle, query reflections, validation, data payloads,
telemetry, and grounded business explanations across all graph nodes.
"""

from typing import TypedDict, Optional, List, Dict, Any


class AgentState(TypedDict, total=False):
    """
    Typed state representation passed across all nodes in the LangGraph workflow.
    Guarantees bounded execution, strict typing, and auditable history.
    """
    # 1. Inputs & Orchestration Guards
    question: str
    step_count: int
    workflow_status: str  # 'in_progress', 'completed', 'rejected', 'needs_clarification', 'failed'
    
    # 2. Question Understanding & Intent
    intent: Optional[str]  # 'analytical_query', 'ambiguous', 'unsafe_injection', 'out_of_scope'
    identified_entities: List[str]
    clarification_message: Optional[str]
    rejection_reason: Optional[str]

    # 3. Schema Grounding
    relevant_schema: Optional[str]
    allowed_tables: List[str]

    # 4. SQL Synthesis & Reflection
    generated_sql: Optional[str]
    assumptions: List[str]
    retry_count: int
    max_retries: int

    # 5. AST Validation (SQLGlot)
    validation_result: Optional[Dict[str, Any]]  # {'is_valid': bool, 'error': Optional[str], 'sanitized_sql': str}

    # 6. Database Execution
    query_execution_result: Optional[List[Dict[str, Any]]]
    columns: Optional[List[str]]
    row_count: int
    execution_time_ms: float

    # 7. Analysis & Grounded Business Narrative
    analysis_summary: Optional[Dict[str, Any]]
    business_insight: Optional[str]

    # 8. Diagnostics & Telemetry
    error_details: Optional[str]
    execution_metadata: Optional[Dict[str, Any]]
