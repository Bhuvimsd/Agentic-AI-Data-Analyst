"""
app/agent/nodes/analyze_results.py
---------------------------------
Node 6: Statistical analysis and aggregation of raw database results.
Extracts empirical distributions, identifies lead records, and flags empty result sets.
"""

from typing import Dict, Any, List
from app.agent.state import AgentState


def analyze_results(state: AgentState) -> AgentState:
    """Computes summary statistics and empirical metrics from query execution results."""
    step_count = state.get("step_count", 0) + 1
    data: List[Dict[str, Any]] = state.get("query_execution_result") or []
    row_count = len(data)

    if row_count == 0:
        return {
            **state,
            "step_count": step_count,
            "analysis_summary": {
                "is_empty": True,
                "row_count": 0,
                "message": "The query executed successfully but returned zero matching records."
            }
        }

    first_row = data[0]
    columns = list(first_row.keys())
    
    # Identify numeric and text columns
    numeric_cols = [c for c in columns if isinstance(first_row[c], (int, float))]
    
    metrics = {
        "is_empty": False,
        "row_count": row_count,
        "columns": columns,
        "lead_record": first_row
    }

    # Compute descriptive statistics on primary numeric metric
    if numeric_cols:
        primary_num_col = numeric_cols[-1]  # Usually the aggregated metric (revenue, spend, count)
        values = [row[primary_num_col] for row in data if isinstance(row.get(primary_num_col), (int, float))]
        if values:
            metrics["primary_metric"] = primary_num_col
            metrics["total_sum"] = round(sum(values), 2)
            metrics["average"] = round(sum(values) / len(values), 2)
            metrics["min_value"] = min(values)
            metrics["max_value"] = max(values)

    return {
        **state,
        "step_count": step_count,
        "analysis_summary": metrics
    }
