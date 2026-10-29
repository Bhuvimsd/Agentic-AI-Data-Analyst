"""
app/agent/validator.py
----------------------
SQL Validation adapter delegating to the production-grade SQLGuard engine.
Maintains backward compatibility for the LangGraph agent workflow.
"""

from typing import Dict, Any, Optional, List
from app.security.sql_guard import sql_guard, SQLGuard, SecurityValidationResult
from app.config import settings


class SQLValidator:
    """
    Adapter bridging LangGraph agent nodes with the hardened SQLGuard engine.
    """

    def __init__(self, guard: Optional[SQLGuard] = None):
        self.guard = guard or sql_guard

    def validate(self, sql_query: str) -> Dict[str, Any]:
        """
        Parses and validates a SQL query using SQLGuard.
        Returns a dict: {'is_valid': bool, 'error': Optional[str], 'sanitized_sql': Optional[str]}
        """
        result: SecurityValidationResult = self.guard.validate(sql_query)
        return {
            "is_valid": result.is_valid,
            "error": result.error,
            "sanitized_sql": result.sanitized_sql,
            "violation_category": result.violation_category,
            "applied_limit": result.applied_limit
        }


# Global singleton validator instance
validator = SQLValidator()
