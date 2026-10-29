"""
app/llm/sql_generator.py
------------------------
Core Natural Language to SQL generator service.
Enforces schema grounding, adversarial prompt injection defense,
structured Pydantic validation, and read-only query guarantees.
"""

import re
import logging
from typing import Optional, List
from app.llm.models import GeneratedSQLResult
from app.llm.client import LLMClient, get_llm_client
from app.llm.prompts import build_system_prompt

logger = logging.getLogger("agentic_ai.sql_generator")

# Obvious mutation keywords for zero-trust pre-filter
MUTATION_PATTERNS = [
    r"\bDROP\s+TABLE\b",
    r"\bTRUNCATE\b",
    r"\bDELETE\s+FROM\b",
    r"\bUPDATE\s+\w+\s+SET\b",
    r"\bALTER\s+TABLE\b",
    r"\bCREATE\s+(TABLE|USER|ROLE)\b",
    r"\bGRANT\s+\w+\b",
    r"\bREVOKE\s+\w+\b",
    r"\bINSERT\s+INTO\b"
]


class SQLGenerator:
    """
    Translates natural-language business questions into safe, structured PostgreSQL queries.
    Never executes queries directly.
    """

    def __init__(self, client: Optional[LLMClient] = None):
        self.client = client or get_llm_client()
        self.system_prompt = build_system_prompt()

    def generate(self, question: str) -> GeneratedSQLResult:
        """
        Converts a business question to a GeneratedSQLResult.
        Applies input sanitization, LLM structured reasoning, and defensive post-checks.
        """
        clean_question = question.strip() if question else ""
        if not clean_question:
            return GeneratedSQLResult(
                sql=None,
                assumptions=[],
                needs_clarification=True,
                clarification_message="Please provide a specific business or analytical question to generate a query.",
                is_safe_query=True
            )

        # 1. Pre-Generation Input Guard (Treat prompt as untrusted)
        for pattern in MUTATION_PATTERNS:
            if re.search(pattern, clean_question, re.IGNORECASE):
                logger.warning(f"Malicious prompt injection / DDL attempt blocked: {clean_question}")
                return GeneratedSQLResult(
                    sql=None,
                    assumptions=[],
                    needs_clarification=False,
                    clarification_message=None,
                    is_safe_query=False,
                    rejection_reason="Data modification statements (INSERT, UPDATE, DELETE, DROP, TRUNCATE, ALTER) are strictly prohibited.",
                    referenced_tables=[]
                )

        # 2. Invoke LLM with Schema Grounding
        try:
            result = self.client.generate_structured(
                prompt=clean_question,
                system_prompt=self.system_prompt,
                response_model=GeneratedSQLResult
            )
        except ConnectionError as ce:
            logger.error(f"LLM connection failure: {ce}")
            raise RuntimeError(f"LLM service is currently unavailable: {str(ce)}")
        except Exception as e:
            logger.error(f"Structured SQL generation failed: {e}")
            raise RuntimeError(f"SQL generation failed: {str(e)}")

        # 3. Defensive Post-Generation Validation
        if result.sql:
            raw_sql = result.sql.strip()
            
            # Must strictly start with SELECT or WITH (for CTEs)
            if not (raw_sql.upper().startswith("SELECT") or raw_sql.upper().startswith("WITH")):
                logger.error(f"LLM generated non-SELECT statement: {raw_sql}")
                return GeneratedSQLResult(
                    sql=None,
                    assumptions=result.assumptions,
                    needs_clarification=False,
                    clarification_message=None,
                    is_safe_query=False,
                    rejection_reason="The generated statement violates the strict read-only SELECT policy.",
                    referenced_tables=[]
                )

            # Block stacked queries (multiple statements separated by semicolons)
            semicolon_count = raw_sql.count(";")
            if semicolon_count > 1 or (semicolon_count == 1 and not raw_sql.endswith(";")):
                logger.error(f"LLM generated stacked/chained queries: {raw_sql}")
                return GeneratedSQLResult(
                    sql=None,
                    assumptions=result.assumptions,
                    needs_clarification=False,
                    clarification_message=None,
                    is_safe_query=False,
                    rejection_reason="Chained or stacked SQL statements are forbidden.",
                    referenced_tables=[]
                )

        return result
