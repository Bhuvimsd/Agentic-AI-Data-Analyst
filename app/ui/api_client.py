"""
app/ui/api_client.py
--------------------
Robust HTTP client bridging the Streamlit dashboard with the FastAPI backend.
Includes automatic local fallback to Python services if the backend server is not running,
ensuring 100% availability for demo and evaluation environments.
"""

import logging
from typing import Dict, Any, Optional, List
import requests
from app.config import settings
from app.database import readonly_engine, check_database_health
from app.services.analytics_service import get_database_schema, execute_predefined_query
from app.agent.workflow import run_agentic_workflow

logger = logging.getLogger("agentic_ai.api_client")


class DashboardAPIClient:
    """
    Client for interacting with the Agentic AI Data Analyst FastAPI service.
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8000", timeout: int = 15):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = {"Content-Type": "application/json"}
        if settings.API_KEY:
            self.headers["X-API-Key"] = settings.API_KEY

    def check_health(self) -> Dict[str, Any]:
        """Probes /health endpoint or falls back to direct database engine check."""
        try:
            resp = requests.get(f"{self.base_url}/health", headers=self.headers, timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                data["source"] = "api"
                return data
        except Exception:
            pass

        # Fallback to direct Python database probe
        health = check_database_health()
        health["source"] = "direct"
        return health

    def fetch_schema(self) -> Dict[str, Any]:
        """Retrieves approved schema metadata from /schema or directly from database inspector."""
        try:
            resp = requests.get(f"{self.base_url}/schema", headers=self.headers, timeout=5)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass

        # Fallback to direct database schema inspector
        with readonly_engine.connect() as conn:
            return get_database_schema(conn).model_dump()

    def query_predefined(self, query_id: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Executes a pre-approved analytical query."""
        payload = {"query_id": query_id, "parameters": params or {}}
        try:
            resp = requests.post(
                f"{self.base_url}/analytics/query",
                json=payload,
                headers=self.headers,
                timeout=self.timeout
            )
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 400:
                return {"success": False, "error": resp.json().get("detail", "Invalid query parameters")}
        except Exception:
            pass

        # Fallback to direct execution
        with readonly_engine.connect() as conn:
            try:
                res = execute_predefined_query(conn, query_id, params or {})
                return res.model_dump()
            except Exception as e:
                return {"success": False, "error": str(e)}

    def query_agent(self, question: str) -> Dict[str, Any]:
        """
        Sends a natural language question through the LangGraph agentic workflow.
        """
        payload = {"question": question}
        try:
            resp = requests.post(
                f"{self.base_url}/analytics/agent/query",
                json=payload,
                headers=self.headers,
                timeout=self.timeout
            )
            if resp.status_code == 200:
                data = resp.json()
                data["source"] = "api"
                return data
        except Exception:
            pass

        # Fallback to direct Python workflow execution
        final_state = run_agentic_workflow(question=question)
        rows = final_state.get("query_execution_result") or []
        cols = final_state.get("columns") or (list(rows[0].keys()) if rows else [])

        return {
            "question": question,
            "status": final_state.get("workflow_status", "failed"),
            "generated_sql": final_state.get("generated_sql"),
            "columns": cols,
            "data": rows,
            "row_count": final_state.get("row_count", len(rows)),
            "execution_time_ms": final_state.get("execution_time_ms", 0.0),
            "business_insight": final_state.get("business_insight"),
            "clarification_message": final_state.get("clarification_message"),
            "error_details": final_state.get("error_details"),
            "retry_count": final_state.get("retry_count", 0),
            "source": "direct"
        }


# Global singleton client
api_client = DashboardAPIClient()
