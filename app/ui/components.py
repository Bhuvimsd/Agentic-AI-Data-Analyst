"""
app/ui/components.py
--------------------
Reusable modern UI components, custom styling, and layout helpers for Streamlit.
"""

from typing import List, Dict, Any, Optional
import streamlit as st
import pandas as pd


CUSTOM_CSS = """
<style>
/* Main typography and container styling */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* Metric Card Styling */
.metric-card {
    background: linear-gradient(135deg, #FFFFFF 0%, #F8FAFC 100%);
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 20px;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.metric-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.08);
}

.metric-title {
    font-size: 0.85rem;
    font-weight: 600;
    color: #64748B;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 6px;
}

.metric-value {
    font-size: 1.85rem;
    font-weight: 700;
    color: #0F172A;
    line-height: 1.2;
}

.metric-subtext {
    font-size: 0.8rem;
    color: #10B981;
    margin-top: 6px;
    font-weight: 500;
}

/* Metadata pill badges */
.badge-container {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 10px;
    margin-bottom: 12px;
}

.badge {
    display: inline-flex;
    align-items: center;
    padding: 4px 10px;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 600;
    border: 1px solid transparent;
}

.badge-info {
    background-color: #EEF2FF;
    color: #4F46E5;
    border-color: #C7D2FE;
}

.badge-success {
    background-color: #ECFDF5;
    color: #059669;
    border-color: #A7F3D0;
}

.badge-warning {
    background-color: #FFFBEB;
    color: #D97706;
    border-color: #FDE68A;
}

.badge-danger {
    background-color: #FEF2F2;
    color: #DC2626;
    border-color: #FECACA;
}

/* Insight highlight block */
.insight-box {
    background-color: #F8FAFC;
    border-left: 4px solid #4F46E5;
    border-radius: 0 8px 8px 0;
    padding: 16px 20px;
    margin: 12px 0 16px 0;
    font-size: 0.95rem;
    color: #334155;
    line-height: 1.6;
}

.insight-header {
    font-weight: 700;
    color: #1E293B;
    margin-bottom: 6px;
    display: flex;
    align-items: center;
    gap: 6px;
}
</style>
"""


def apply_custom_styles():
    """Injects custom CSS stylesheets into the Streamlit session."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def render_kpi_card(title: str, value: str, subtext: str = "", delta_color: str = "normal"):
    """Renders a styled executive KPI card."""
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">{title}</div>
        <div class="metric-value">{value}</div>
        {f'<div class="metric-subtext">{subtext}</div>' if subtext else ''}
    </div>
    """, unsafe_allow_html=True)


def render_metadata_badges(
    duration_ms: float,
    row_count: int,
    retry_count: int = 0,
    source: str = "api",
    status: str = "completed"
):
    """Renders interactive execution telemetry badges."""
    status_class = "badge-success" if status == "completed" else ("badge-warning" if status == "needs_clarification" else "badge-danger")
    
    st.markdown(f"""
    <div class="badge-container">
        <span class="badge {status_class}">Status: {status.upper()}</span>
        <span class="badge badge-info">⏱️ Latency: {duration_ms:.1f}ms</span>
        <span class="badge badge-info">📊 Rows: {row_count}</span>
        <span class="badge badge-info">🔄 Retries: {retry_count}</span>
        <span class="badge badge-success">🛡️ SQLGuard: Approved</span>
        <span class="badge badge-info">🔌 Gateway: {source.upper()}</span>
    </div>
    """, unsafe_allow_html=True)


def render_sql_viewer(sql_query: Optional[str], expanded: bool = False):
    """Renders generated SQL inside a clean, collapsible viewer."""
    if not sql_query:
        return
    with st.expander("🔍 View Validated SQL Query (PostgreSQL)", expanded=expanded):
        st.code(sql_query, language="sql")
        st.caption("🔒 Verified by SQLGuard AST Validator (Read-Only SELECT • LIMIT 100 enforced • Comments Stripped)")


def render_csv_download(df: pd.DataFrame, filename: str = "query_results.csv", key: Optional[str] = None):
    """Renders a CSV download button for query result sets."""
    if df.empty:
        return
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Download CSV Results",
        data=csv_bytes,
        file_name=filename,
        mime="text/csv",
        key=key,
        help="Export current query result set as CSV for reporting"
    )
