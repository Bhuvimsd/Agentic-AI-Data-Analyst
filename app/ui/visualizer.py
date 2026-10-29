"""
app/ui/visualizer.py
--------------------
Intelligent Plotly visualization generator and auto-chart recommender for business datasets.
Rules enforced:
- Line charts for chronological / time-series trends (order_date, order_month).
- Bar charts for categorical comparisons (products, categories, regions, payment methods).
- KPI cards / scalar displays for aggregate totals and averages.
- Graceful handling of empty or single-row result sets.
- Currency formatting (INR ₹) and non-misleading axes.
"""

from typing import Optional, Dict, Any, Tuple
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Curated, accessible color palette
CHART_COLORS = [
    "#4F46E5",  # Indigo
    "#10B981",  # Emerald
    "#F59E0B",  # Amber
    "#EC4899",  # Pink
    "#06B6D4",  # Cyan
    "#8B5CF6",  # Violet
    "#3B82F6",  # Blue
]

DATE_KEYWORDS = {"date", "month", "year", "day", "mth", "period", "order_date", "order_month"}
METRIC_KEYWORDS = {"revenue", "total", "sales", "price", "amount", "spend", "value", "aov", "count", "quantity", "units"}


def is_currency_column(col_name: str) -> bool:
    """Checks if a column represents a financial metric in INR."""
    c_lower = col_name.lower()
    return any(w in c_lower for w in ["revenue", "sales", "amount", "price", "spend", "value", "aov", "total_rev", "margin"])


def format_currency(val: float) -> str:
    """Formats numeric values into clean INR string representation."""
    if abs(val) >= 10_000_000:
        return f"₹{val / 10_000_000:.2f} Cr"
    elif abs(val) >= 100_000:
        return f"₹{val / 100_000:.2f} L"
    elif abs(val) >= 1_000:
        return f"₹{val / 1_000:.1f}k"
    return f"₹{val:,.2f}"


def inspect_dataframe_dimensions(df: pd.DataFrame) -> Dict[str, Any]:
    """Analyzes columns, data types, and row count to categorize dimensions."""
    if df.empty:
        return {"empty": True}

    date_cols = []
    cat_cols = []
    num_cols = []

    for col in df.columns:
        c_lower = col.lower()
        if any(dk in c_lower for dk in DATE_KEYWORDS):
            date_cols.append(col)
        elif pd.api.types.is_numeric_dtype(df[col]):
            num_cols.append(col)
        else:
            cat_cols.append(col)

    # In case numeric types are stored as strings of numbers
    if not num_cols:
        for col in df.columns:
            try:
                pd.to_numeric(df[col].dropna())
                num_cols.append(col)
                if col in cat_cols:
                    cat_cols.remove(col)
            except Exception:
                pass

    return {
        "empty": False,
        "row_count": len(df),
        "date_cols": date_cols,
        "cat_cols": cat_cols,
        "num_cols": num_cols
    }


def auto_recommend_chart_type(df: pd.DataFrame, question: str = "") -> str:
    """
    Intelligently determines the most suitable visualization for a dataset:
    - 'kpi'       : Single scalar or single row with a numeric metric
    - 'line'      : Chronological date/month trend
    - 'bar'       : Categorical comparison
    - 'donut'     : Categorical distribution with <= 6 slices
    - 'table'     : Complex multi-column records without dominant numeric axis
    """
    dims = inspect_dataframe_dimensions(df)
    if dims.get("empty"):
        return "none"

    row_count = dims["row_count"]
    num_cols = dims["num_cols"]
    date_cols = dims["date_cols"]
    cat_cols = dims["cat_cols"]

    # 1. Single scalar KPI
    if row_count == 1 and len(num_cols) >= 1 and len(df.columns) <= 3:
        return "kpi"

    # 2. Time-series trend (presence of date column + numeric metric)
    if date_cols and num_cols:
        return "line"

    # 3. Categorical comparison
    if cat_cols and num_cols:
        if row_count <= 6 and "category" in [c.lower() for c in cat_cols]:
            return "bar"  # Bar is clear and non-misleading
        return "bar"

    # 4. Multi-numeric
    if len(num_cols) >= 2 and cat_cols:
        return "bar"

    return "table"


def build_plotly_figure(
    df: pd.DataFrame, 
    chart_type: str = "auto",
    title: Optional[str] = None
) -> Optional[go.Figure]:
    """
    Renders an interactive, polished Plotly figure matching design requirements.
    """
    if df.empty:
        return None

    dims = inspect_dataframe_dimensions(df)
    if dims.get("empty"):
        return None

    chosen_type = auto_recommend_chart_type(df) if chart_type == "auto" else chart_type.lower()
    date_cols = dims["date_cols"]
    cat_cols = dims["cat_cols"]
    num_cols = dims["num_cols"]

    # Base styling layout
    base_layout = dict(
        title=dict(text=title or "", font=dict(size=16, family="Inter, sans-serif", color="#1E293B")),
        template="plotly_white",
        margin=dict(l=40, r=40, t=50, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hoverlabel=dict(bgcolor="white", font_size=13, font_family="Inter, sans-serif"),
        font=dict(family="Inter, sans-serif", color="#475569")
    )

    # --------------------------------------------------------------------------
    # 1. LINE / AREA CHART (Time Series)
    # --------------------------------------------------------------------------
    if chosen_type in ("line", "area"):
        x_col = date_cols[0] if date_cols else (cat_cols[0] if cat_cols else df.columns[0])
        y_col = num_cols[0] if num_cols else df.columns[1]

        is_curr = is_currency_column(y_col)
        hover_template = f"<b>%{{x}}</b><br>{y_col}: " + ("₹%{y:,.2f}" if is_curr else "%{y:,}") + "<extra></extra>"

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df[x_col],
            y=df[y_col],
            mode="lines+markers",
            name=y_col.replace("_", " ").title(),
            line=dict(color="#4F46E5", width=3, shape="spline"),
            marker=dict(size=8, color="#4F46E5", line=dict(width=2, color="white")),
            fill="tozeroy" if chosen_type == "area" else "none",
            fillcolor="rgba(79, 70, 229, 0.1)",
            hovertemplate=hover_template
        ))

        fig.update_layout(
            **base_layout,
            xaxis=dict(title=x_col.replace("_", " ").title(), showgrid=False),
            yaxis=dict(
                title=y_col.replace("_", " ").title(),
                tickprefix="₹" if is_curr else "",
                showgrid=True,
                gridcolor="#F1F5F9"
            )
        )
        return fig

    # --------------------------------------------------------------------------
    # 2. BAR CHART (Categorical Comparison)
    # --------------------------------------------------------------------------
    elif chosen_type == "bar":
        x_col = cat_cols[0] if cat_cols else df.columns[0]
        y_col = num_cols[0] if num_cols else df.columns[-1]

        is_curr = is_currency_column(y_col)
        # Determine orientation: horizontal if category labels are long (> 15 chars)
        max_label_len = df[x_col].astype(str).str.len().max() if len(df) > 0 else 0
        horizontal = max_label_len > 18 or len(df) > 10

        fig = go.Figure()

        if horizontal:
            df_sorted = df.sort_values(by=y_col, ascending=True)
            hover_template = f"<b>%{{y}}</b><br>{y_col}: " + ("₹%{x:,.2f}" if is_curr else "%{x:,}") + "<extra></extra>"
            fig.add_trace(go.Bar(
                x=df_sorted[y_col],
                y=df_sorted[x_col],
                orientation="h",
                marker=dict(
                    color=df_sorted[y_col],
                    colorscale="Viridis",
                    line=dict(width=0)
                ),
                hovertemplate=hover_template
            ))
            fig.update_layout(
                **base_layout,
                xaxis=dict(title=y_col.replace("_", " ").title(), tickprefix="₹" if is_curr else "", showgrid=True, gridcolor="#F1F5F9"),
                yaxis=dict(title=None, showgrid=False)
            )
        else:
            hover_template = f"<b>%{{x}}</b><br>{y_col}: " + ("₹%{y:,.2f}" if is_curr else "%{y:,}") + "<extra></extra>"
            fig.add_trace(go.Bar(
                x=df[x_col],
                y=df[y_col],
                marker=dict(
                    color=CHART_COLORS[0],
                    cornerradius=6
                ),
                hovertemplate=hover_template
            ))
            fig.update_layout(
                **base_layout,
                xaxis=dict(title=x_col.replace("_", " ").title(), showgrid=False),
                yaxis=dict(
                    title=y_col.replace("_", " ").title(),
                    tickprefix="₹" if is_curr else "",
                    showgrid=True,
                    gridcolor="#F1F5F9"
                )
            )

        return fig

    # --------------------------------------------------------------------------
    # 3. DONUT / PIE CHART (Distribution <= 7 slices)
    # --------------------------------------------------------------------------
    elif chosen_type in ("donut", "pie"):
        cat_col = cat_cols[0] if cat_cols else df.columns[0]
        val_col = num_cols[0] if num_cols else df.columns[-1]

        fig = go.Figure(data=[go.Pie(
            labels=df[cat_col],
            values=df[val_col],
            hole=0.45 if chosen_type == "donut" else 0.0,
            marker=dict(colors=CHART_COLORS),
            textinfo="percent+label",
            hoverinfo="label+value+percent"
        )])
        fig.update_layout(**base_layout)
        return fig

    # Default fallback: return None (handled via standard st.dataframe table)
    return None
