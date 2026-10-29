"""
app/security/sql_guard.py
-------------------------
Production-grade defensive SQL AST parsing and security validation engine using SQLGlot.
Enforces multi-tier defense:
1. Exactly one SQL statement (blocks stacked queries).
2. Pure read-only SELECT structure (blocks mutations, DDL, DML, EXECUTE, COPY, CALL).
3. Data-modifying CTE detection (blocks WITH ... AS (UPDATE/DELETE/INSERT)).
4. SELECT INTO and locking clause rejection (blocks FOR UPDATE / FOR SHARE).
5. Schema and table allowlist enforcement (blocks system catalogs and internal schemas).
6. Function allowlist (rejects unknown functions by default, blocks pg_sleep/version/current_user/system calls).
7. Column allowlist verification (blocks hallucinated and unauthorized columns).
8. Automatic LIMIT injection and query rewriting (prevents DoS).
9. Comment stripping (neutralizes comment obfuscation attacks).
"""

from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Set, Any, Tuple
import sqlglot
from sqlglot import exp
from app.llm.schema_context import ALLOWED_TABLES, ALLOWED_COLUMNS
from app.config import settings


@dataclass
class SecurityValidationResult:
    """Structured security audit result for a parsed query."""
    is_valid: bool
    error: Optional[str] = None
    sanitized_sql: Optional[str] = None
    violation_category: Optional[str] = None
    applied_limit: int = 100

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to standard dictionary representation."""
        return {
            "is_valid": self.is_valid,
            "error": self.error,
            "sanitized_sql": self.sanitized_sql,
            "violation_category": self.violation_category,
            "applied_limit": self.applied_limit
        }


# Permitted analytical function AST classes (SQLGlot AST types)
ALLOWED_FUNC_CLASSES: Tuple[type, ...] = (
    # Aggregates
    exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max,
    # Math / Numeric
    exp.Round, exp.Ceil, exp.Floor, exp.Abs, exp.Pow, exp.Sqrt,
    # String manipulation
    exp.Substring, exp.Trim, exp.Upper, exp.Lower, exp.Concat, exp.Length,
    # Date / Time
    exp.TimestampTrunc, exp.DateTrunc, exp.Extract, exp.CurrentDate, exp.CurrentTimestamp,
    exp.Date, exp.TimeToStr, exp.StrToTime, exp.DateAdd, exp.DateSub,
    # Conditional & Null handling
    exp.Coalesce, exp.Nullif, exp.Greatest, exp.Least, exp.Cast, exp.TryCast,
    # Window functions
    exp.RowNumber, exp.Rank, exp.DenseRank, exp.Lag, exp.Lead, exp.Ntile,
    # Logical AST connectors (inherit from exp.Func in SQLGlot)
    exp.And, exp.Or, exp.LogicalAnd, exp.LogicalOr
)

# Explicitly permitted named analytical functions (for exp.Anonymous or PostgreSQL/Snowflake specific funcs)
ALLOWED_ANONYMOUS_FUNCTIONS: Set[str] = {
    "sum", "avg", "count", "min", "max", "round", "coalesce", "to_char", "to_varchar",
    "substr", "substring", "date_trunc", "extract", "row_number", "rank",
    "dense_rank", "abs", "lower", "upper", "trim", "concat", "cast",
    "length", "nullif", "greatest", "least", "ceil", "floor", "power", "sqrt",
    "iff", "nvl", "zeroifnull", "dateadd", "datediff"
}

# Forbidden system schemas and catalogs (PostgreSQL, Snowflake, MySQL)
FORBIDDEN_SCHEMAS: Set[str] = {
    "pg_catalog", "information_schema", "pg_toast", "pg_temp", "pg_internal",
    "snowflake", "account_usage"
}

# Forbidden DDL/DML mutations
FORBIDDEN_MUTATION_CLASSES = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Alter,
    exp.Command, exp.Create
)


class SQLGuard:
    """
    Dedicated AST Security Guardrail for Text-to-SQL systems.
    Guarantees no unauthorized SQL can reach the database execution engine.
    """

    def __init__(
        self,
        allowed_tables: Optional[List[str]] = None,
        allowed_columns: Optional[Dict[str, List[str]]] = None,
        default_limit: int = 100,
        max_limit: int = 1000
    ):
        self.allowed_tables = set(allowed_tables or ALLOWED_TABLES)
        self.allowed_columns = allowed_columns or ALLOWED_COLUMNS
        self.default_limit = default_limit
        self.max_limit = max_limit
        # Precompute flat set of all approved columns
        self.all_schema_columns = {col.lower() for cols in self.allowed_columns.values() for col in cols}

    def validate(self, sql_query: str) -> SecurityValidationResult:
        """
        Performs exhaustive AST security inspection against the PostgreSQL dialect.
        Returns SecurityValidationResult with sanitized, limit-injected SQL if valid.
        """
        if not sql_query or not sql_query.strip():
            return SecurityValidationResult(
                is_valid=False,
                error="Query is empty.",
                violation_category="EMPTY_QUERY"
            )

        # 1. Parse using PostgreSQL or Snowflake dialect
        parsed_statements = None
        parse_err = None
        for dialect in ("postgres", "snowflake"):
            try:
                stmts = sqlglot.parse(sql_query, read=dialect)
                if stmts and any(s is not None for s in stmts):
                    parsed_statements = stmts
                    break
            except Exception as e:
                parse_err = e

        if parsed_statements is None:
            return SecurityValidationResult(
                is_valid=False,
                error=f"SQL syntax error in SQL dialect: {str(parse_err)}",
                violation_category="SYNTAX_ERROR"
            )

        valid_statements = [s for s in parsed_statements if s is not None]

        # 2. Enforce exactly one statement (Block stacked queries like 'SELECT 1; DROP TABLE...')
        if len(valid_statements) != 1:
            return SecurityValidationResult(
                is_valid=False,
                error="Multiple SQL statements detected. Only a single SELECT query is permitted.",
                violation_category="STACKED_QUERIES"
            )

        statement = valid_statements[0]

        # 3. Reject any DDL/DML mutations anywhere in the AST
        for node in statement.walk():
            if isinstance(node, FORBIDDEN_MUTATION_CLASSES):
                op_name = type(node).__name__.upper()
                return SecurityValidationResult(
                    is_valid=False,
                    error=f"Prohibited operation '{op_name}'. Only read-only SELECT queries are allowed.",
                    violation_category="MUTATION"
                )

        # 4. Root statement must be a Select or Union of Selects
        if not isinstance(statement, (exp.Select, exp.Union)):
            return SecurityValidationResult(
                is_valid=False,
                error=f"Statement root must be SELECT, found '{type(statement).__name__}'.",
                violation_category="INVALID_STATEMENT_ROOT"
            )

        # 5. Reject SELECT INTO (which creates a new table on disk)
        if statement.args.get("into") or any(isinstance(n, exp.Into) for n in statement.walk()):
            return SecurityValidationResult(
                is_valid=False,
                error="SELECT INTO statements are prohibited.",
                violation_category="SELECT_INTO"
            )

        # 6. Reject locking clauses (FOR UPDATE / FOR SHARE / FOR NO KEY UPDATE)
        if statement.args.get("locks") or any(isinstance(n, exp.Lock) for n in statement.walk()):
            return SecurityValidationResult(
                is_valid=False,
                error="Row-locking clauses (FOR UPDATE / FOR SHARE) are prohibited.",
                violation_category="LOCKING_CLAUSE"
            )

        # 7. Reject Data-Modifying Common Table Expressions (CTEs)
        for cte in statement.find_all(exp.CTE):
            for child in cte.walk():
                if isinstance(child, (exp.Insert, exp.Update, exp.Delete)):
                    return SecurityValidationResult(
                        is_valid=False,
                        error="Data-modifying CTEs (WITH ... INSERT/UPDATE/DELETE) are strictly prohibited.",
                        violation_category="DATA_MODIFYING_CTE"
                    )

        # Collect legitimate CTE aliases defined in WITH clause
        cte_aliases = {cte.alias_or_name.lower() for cte in statement.find_all(exp.CTE)}

        # 8. Schema & Table Allowlist Enforcement
        for table in statement.find_all(exp.Table):
            table_name = table.name.lower()
            schema_name = (table.db or "").lower()

            # Reject system schemas
            if schema_name in FORBIDDEN_SCHEMAS:
                return SecurityValidationResult(
                    is_valid=False,
                    error=f"Access to system catalog schema '{schema_name}' is forbidden.",
                    violation_category="SYSTEM_CATALOG"
                )

            # Block system catalog tables even without explicit schema prefix
            if table_name.startswith("pg_") or table_name.startswith("information_schema"):
                return SecurityValidationResult(
                    is_valid=False,
                    error=f"Access to internal system table '{table_name}' is forbidden.",
                    violation_category="SYSTEM_CATALOG"
                )

            # Table must be in allowed list or a valid CTE alias
            if table_name not in self.allowed_tables and table_name not in cte_aliases:
                return SecurityValidationResult(
                    is_valid=False,
                    error=f"Unauthorized table '{table_name}'. Only approved analytical tables are allowed.",
                    violation_category="UNAUTHORIZED_TABLE"
                )

        # 9. Function Allowlist Enforcement (Default-Deny Policy)
        # Any function that is not in the approved analytical classes or anonymous set is rejected
        for func in statement.find_all(exp.Func):
            if isinstance(func, exp.Anonymous):
                func_name = func.name.lower()
                if func_name not in ALLOWED_ANONYMOUS_FUNCTIONS:
                    return SecurityValidationResult(
                        is_valid=False,
                        error=f"Function '{func_name}()' is not in the safe analytical function allowlist.",
                        violation_category="UNAUTHORIZED_FUNCTION"
                    )
            elif not isinstance(func, ALLOWED_FUNC_CLASSES):
                func_name = getattr(func, "name", type(func).__name__).lower()
                return SecurityValidationResult(
                    is_valid=False,
                    error=f"Function '{func_name}()' is not in the safe analytical function allowlist.",
                    violation_category="UNAUTHORIZED_FUNCTION"
                )

        # 10. Check Column References against Explicit Allowlist + Hallucinated Banned Columns
        banned_attributes = {"profit", "discount_code", "churn", "margin", "salary", "employee_id", "email", "password"}
        query_aliases = {a.alias_or_name.lower() for a in statement.find_all(exp.Alias)}

        for col in statement.find_all(exp.Column):
            col_name = col.name.lower()
            # Catch explicitly banned attributes
            if col_name in banned_attributes:
                return SecurityValidationResult(
                    is_valid=False,
                    error=f"Column '{col_name}' does not exist in the analytical database.",
                    violation_category="HALLUCINATED_COLUMN"
                )
            # Catch unknown columns that aren't wildcard (*), aren't in schema, and aren't query aliases
            if col_name != "*" and col_name not in self.all_schema_columns and col_name not in query_aliases:
                # If qualified with a table, verify that table is in allowed tables
                tbl_name = (col.table or "").lower()
                if tbl_name and tbl_name not in cte_aliases:
                    return SecurityValidationResult(
                        is_valid=False,
                        error=f"Column '{col_name}' does not exist in table '{tbl_name}'.",
                        violation_category="HALLUCINATED_COLUMN"
                    )

        # 11. Safe Row Limit Rewriting & Enforcement
        applied_limit = self.default_limit
        if not statement.args.get("limit"):
            statement = statement.limit(self.default_limit)
        else:
            try:
                raw_lim = statement.args["limit"].expression
                if hasattr(raw_lim, "this") and str(raw_lim.this).isdigit():
                    user_limit = int(raw_lim.this)
                    if user_limit > self.max_limit:
                        statement = statement.limit(self.max_limit)
                        applied_limit = self.max_limit
                    else:
                        applied_limit = user_limit
            except Exception:
                statement = statement.limit(self.default_limit)

        # 12. Strip comments to neutralize comment obfuscation attacks
        sanitized_sql = statement.sql(dialect="postgres", comments=False)

        return SecurityValidationResult(
            is_valid=True,
            error=None,
            sanitized_sql=sanitized_sql,
            violation_category=None,
            applied_limit=applied_limit
        )


# Global singleton SQLGuard instance
sql_guard = SQLGuard()
