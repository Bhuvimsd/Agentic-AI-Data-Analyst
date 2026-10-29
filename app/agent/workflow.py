"""
app/agent/workflow.py
---------------------
Stateful, bounded LangGraph agent workflow for Agentic AI Data Analyst.
Orchestrates:
START -> understand_question -> retrieve_schema -> generate_sql -> validate_sql 
      -> execute_query -> analyze_results -> generate_insights -> END
Includes defensive routing, bounded retries (max 2), and loop termination guards.
"""

import logging
from typing import Literal, Optional
from langgraph.graph import StateGraph, START, END
from app.agent.state import AgentState
from app.agent.nodes.understand_question import understand_question
from app.agent.nodes.retrieve_schema import retrieve_schema
from app.agent.nodes.generate_sql import generate_sql
from app.agent.nodes.validate_sql import validate_sql
from app.agent.nodes.execute_query import execute_query
from app.agent.nodes.analyze_results import analyze_results
from app.agent.nodes.generate_insights import generate_insights
from app.agent.nodes.handle_error import handle_error

logger = logging.getLogger("agentic_ai.workflow")
MAX_WORKFLOW_STEPS = 15


# ------------------------------------------------------------------------------
# Conditional Routing Functions
# ------------------------------------------------------------------------------
def route_after_understanding(state: AgentState) -> Literal["retrieve_schema", "handle_error"]:
    """Routes from understand_question to schema retrieval or early error/clarification."""
    if state.get("step_count", 0) >= MAX_WORKFLOW_STEPS:
        return "handle_error"
    if state.get("workflow_status") in ("rejected", "needs_clarification", "failed"):
        return "handle_error"
    return "retrieve_schema"


def route_after_generation(state: AgentState) -> Literal["validate_sql", "handle_error"]:
    """Routes from generate_sql to validation or handles generation failure."""
    if state.get("step_count", 0) >= MAX_WORKFLOW_STEPS:
        return "handle_error"
    if state.get("workflow_status") in ("rejected", "needs_clarification", "failed"):
        return "handle_error"
    if not state.get("generated_sql"):
        return "handle_error"
    return "validate_sql"


def route_after_validation(state: AgentState) -> Literal["execute_query", "generate_sql", "handle_error"]:
    """
    Evaluates AST validation.
    If valid -> execute_query.
    If invalid and retries remaining -> loop back to generate_sql for reflection.
    If retries exhausted -> handle_error.
    """
    if state.get("step_count", 0) >= MAX_WORKFLOW_STEPS:
        return "handle_error"

    val_result = state.get("validation_result") or {}
    if val_result.get("is_valid"):
        return "execute_query"

    # Reflection loop check
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 2)
    if retry_count <= max_retries and state.get("workflow_status") == "in_progress":
        logger.info(f"Validation failed. Triggering self-correction retry {retry_count}/{max_retries}...")
        return "generate_sql"

    return "handle_error"


def route_after_execution(state: AgentState) -> Literal["analyze_results", "generate_sql", "handle_error"]:
    """
    Evaluates query execution.
    If successful -> analyze_results.
    If execution failed and retries remaining -> self-healing retry to generate_sql.
    Else -> handle_error.
    """
    if state.get("step_count", 0) >= MAX_WORKFLOW_STEPS:
        return "handle_error"

    if state.get("error_details") and state.get("workflow_status") != "failed":
        retry_count = state.get("retry_count", 0)
        max_retries = state.get("max_retries", 2)
        if retry_count <= max_retries:
            logger.info(f"Execution failed. Triggering database self-healing retry {retry_count}/{max_retries}...")
            return "generate_sql"

    if state.get("workflow_status") == "failed" or state.get("query_execution_result") is None:
        return "handle_error"

    return "analyze_results"


# ------------------------------------------------------------------------------
# Graph Construction & Compilation
# ------------------------------------------------------------------------------
def create_agent_workflow(engine=None, client=None):
    """
    Builds and compiles the bounded LangGraph state graph.
    Injects custom database engine or LLM client fixtures for testing.
    """
    workflow = StateGraph(AgentState)

    # Register Nodes
    workflow.add_node("understand_question", understand_question)
    workflow.add_node("retrieve_schema", retrieve_schema)
    workflow.add_node("generate_sql", lambda s: generate_sql(s, client=client))
    workflow.add_node("validate_sql", validate_sql)
    workflow.add_node("execute_query", lambda s: execute_query(s, engine=engine))
    workflow.add_node("analyze_results", analyze_results)
    workflow.add_node("generate_insights", generate_insights)
    workflow.add_node("handle_error", handle_error)

    # Edge: START -> understand_question
    workflow.add_edge(START, "understand_question")

    # Conditional: understand_question -> retrieve_schema OR handle_error
    workflow.add_conditional_edges(
        "understand_question",
        route_after_understanding,
        {
            "retrieve_schema": "retrieve_schema",
            "handle_error": "handle_error"
        }
    )

    # Edge: retrieve_schema -> generate_sql
    workflow.add_edge("retrieve_schema", "generate_sql")

    # Conditional: generate_sql -> validate_sql OR handle_error
    workflow.add_conditional_edges(
        "generate_sql",
        route_after_generation,
        {
            "validate_sql": "validate_sql",
            "handle_error": "handle_error"
        }
    )

    # Conditional: validate_sql -> execute_query OR generate_sql (retry) OR handle_error
    workflow.add_conditional_edges(
        "validate_sql",
        route_after_validation,
        {
            "execute_query": "execute_query",
            "generate_sql": "generate_sql",
            "handle_error": "handle_error"
        }
    )

    # Conditional: execute_query -> analyze_results OR generate_sql (retry) OR handle_error
    workflow.add_conditional_edges(
        "execute_query",
        route_after_execution,
        {
            "analyze_results": "analyze_results",
            "generate_sql": "generate_sql",
            "handle_error": "handle_error"
        }
    )

    # Edge: analyze_results -> generate_insights
    workflow.add_edge("analyze_results", "generate_insights")

    # Terminal Edges
    workflow.add_edge("generate_insights", END)
    workflow.add_edge("handle_error", END)

    return workflow.compile()


# Global compiled workflow instance
compiled_agent_app = create_agent_workflow()


def run_agentic_workflow(
    question: str,
    engine=None,
    client=None
) -> AgentState:
    """
    Public entry point to execute the Agentic AI workflow for a user question.
    Returns the final state with SQL, data, insights, and telemetry.
    """
    app = create_agent_workflow(engine=engine, client=client)
    initial_state: AgentState = {
        "question": question,
        "step_count": 0,
        "workflow_status": "in_progress",
        "retry_count": 0,
        "max_retries": 2
    }

    final_state = app.invoke(initial_state)
    return final_state
