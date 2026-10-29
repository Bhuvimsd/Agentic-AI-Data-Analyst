"""
app/agent/validator.py
----------------------
Defensive SQL AST parsing and security validation engine using SQLGlot.
Enforces single-statement SELECT guarantees, table/column whitelisting,
banned function filters, and automatic LIMIT 100 injection.
"""

from typing import Dict, Any, List, Set, Optional
import sqlglot
from sqlglot import exp
from app.llm.schema_context import ALLOWED_TABLES, ALLOWED_COLUMNS
from app.config import settings

FORBIDDEN_FUNCTIONS: Set[str] = {
    "pg_sleep", "pg_read_file", "pg_write_file", "system", "version",
    "current_user", "session_user", "pg_terminate_backend", "pg_cancel_backend"
}

FORBIDDEN_EXPRESSIONS = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Alter,
    exp.Command, exp.Create
)


class SQLValidator:
    """
    Multi-layer AST validator ensuring only safe, grounded PostgreSQL SELECT queries execute.
    """

    def __init__(self, allowed_tables: Optional[List[str]] = None):
        self.allowed_tables = set(allowed_tables or ALLOWED_TABLES)

    def validate(self, sql_query: str) -> Dict[str, Any]:
        """
        Parses and validates a SQL query.
        Returns a dict: {'is_valid': bool, 'error': Optional[str], 'sanitized_sql': Optional[str]}
        """
        if not sql_query or not sql_query.strip():
            return {
                "is_valid": False,
                "error": "Query is empty.",
                "sanitized_sql": None
            }

        # 1. Parse into AST using PostgreSQL dialect
        try:
            parsed_statements = sqlglot.parse(sql_query, read="postgres")
        except Exception as e:
            return {
                "is_valid": False,
                "error": f"SQL syntax error: {str(e)}",
                "sanitized_sql": None
            }

        valid_statements = [s for s in parsed_statements if s is not None]

        # 2. Enforce exactly one statement (Block stacked queries)
        if len(valid_statements) != 1:
            return {
                "is_valid": False,
                "error": "Multiple statements detected. Only a single query is permitted.",
                "sanitized_sql": None
            }

        statement = valid_statements[0]

        # 3. Disallow DDL / DML mutations anywhere in AST
        for node in statement.walk():
            if isinstance(node, FORBIDDEN_EXPRESSIONS):
                return {
                    "is_valid": False,
                    "error": f"Prohibited operation '{type(node).__name__}'. Only read-only SELECT queries are allowed.",
                    "sanitized_sql": None
                }

        # 4. Root must be a SELECT expression (or Union of Selects)
        if not isinstance(statement, (exp.Select, exp.Union)):
            return {
                "is_valid": False,
                "error": f"Invalid statement type '{type(statement).__name__}'. Only SELECT statements are permitted.",
                "sanitized_sql": None
            }

        # 5. Extract Common Table Expressions (CTEs) to allow internal CTE alias lookups
        cte_names = set()
        with_clause = statement.args.get("with")
        if with_clause:
            for cte in with_clause.expressions:
                cte_names.add(cte.alias_or_name.lower())

        # 6. Table Whitelist Enforcement
        for table in statement.find_all(exp.Table):
            table_name = table.name.lower()
            if table_name not in self.allowed_tables and table_name not in cte_names:
                return {
                    "is_valid": False,
                    "error": f"Unauthorized table '{table_name}'. Only approved analytical tables are allowed.",
                    "sanitized_sql": None
                }

        # 7. Check for Prohibited Functions
        for func in statement.find_all(exp.Anonymous):
            func_name = func.name.lower()
            if func_name in FORBIDDEN_FUNCTIONS:
                return {
                    "is_valid": False,
                    "error": f"Prohibited system function '{func_name}()' detected.",
                    "sanitized_sql": None
                }

        # 8. Check for Hallucinated Columns (Disallow known missing attributes)
        banned_columns = {"profit", "discount_code", "churn", "margin", "salary", "employee_id", "email"}
        for col in statement.find_all(exp.Column):
            col_name = col.name.lower()
            if col_name in banned_columns:
                return {
                    "is_valid": False,
                    "error": f"Column '{col_name}' does not exist in the analytical schema.",
                    "sanitized_sql": None
                }

        # 9. Enforce / Inject Safety LIMIT
        # If no LIMIT exists, automatically append LIMIT 100 to prevent Denial of Service
        if not statement.args.get("limit"):
            statement = statement.limit(settings.DEFAULT_ROW_LIMIT)
        else:
            # If user limit exceeds MAX_ROW_LIMIT, clamp it
            try:
                current_limit = int(statement.args["limit"].expression.this)
                if current_limit > settings.MAX_ROW_LIMIT:
                    statement = statement.limit(settings.MAX_ROW_LIMIT)
            except Exception:
                pass

        sanitized_sql = statement.sql(dialect="postgres")

        return {
            "is_valid": True,
            "error": None,
            "sanitized_sql": sanitized_sql
        }


# Global singleton validator instance
validator = SQLValidator()
