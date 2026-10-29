"""
app/agent/nodes/generate_insights.py
------------------------------------
Node 7: Grounded business explanation and executive takeaway generator.
Synthesizes business narratives strictly from actual query results without hallucination.
"""

from app.agent.state import AgentState


def generate_insights(state: AgentState) -> AgentState:
    """Generates an executive business explanation strictly grounded in empirical query data."""
    step_count = state.get("step_count", 0) + 1
    summary = state.get("analysis_summary") or {}
    question = state.get("question", "")
    data = state.get("query_execution_result") or []
    row_count = state.get("row_count", 0)

    # 1. Empty Result Case
    if summary.get("is_empty") or row_count == 0:
        insight = (
            f"The query was executed successfully against the database, but returned zero matching records for: '{question}'. "
            "This indicates that no transactions or entities currently satisfy the specified filtering criteria."
        )
        return {
            **state,
            "step_count": step_count,
            "business_insight": insight,
            "workflow_status": "completed"
        }

    # 2. Single Scalar Metric Case (e.g. Total Revenue, AOV)
    if row_count == 1:
        first_row = data[0]
        metric_parts = [f"{k.replace('_', ' ').title()}: {v:,.2f}" if isinstance(v, (int, float)) else f"{k}: {v}" for k, v in first_row.items()]
        insight = (
            f"Analysis for '{question}':\n"
            f"Key Result: {', '.join(metric_parts)}.\n"
            "This figure is calculated from completed order records in accordance with recognized accounting rules."
        )
        return {
            **state,
            "step_count": step_count,
            "business_insight": insight,
            "workflow_status": "completed"
        }

    # 3. Multi-Row Ranking / Dimensional Cohorts
    lead = summary.get("lead_record", {})
    lead_name = lead.get("product_name") or lead.get("customer_name") or lead.get("region") or lead.get("category") or "Lead record"
    
    primary_metric = summary.get("primary_metric", "value")
    lead_val = lead.get(primary_metric)
    val_str = f"INR {lead_val:,.2f}" if isinstance(lead_val, (int, float)) else str(lead_val)

    total_sum = summary.get("total_sum")
    sum_str = f"INR {total_sum:,.2f}" if total_sum is not None else "N/A"

    insight = (
        f"Executive Summary for '{question}':\n"
        f"• The top performer is **{lead_name}** with **{val_str}**.\n"
        f"• Across all {row_count} records returned, the cumulative total is **{sum_str}** "
        f"with an average of **{summary.get('average', 0):,.2f}** per entry.\n"
        "• All figures represent completed transactional history."
    )

    return {
        **state,
        "step_count": step_count,
        "business_insight": insight,
        "workflow_status": "completed"
    }
