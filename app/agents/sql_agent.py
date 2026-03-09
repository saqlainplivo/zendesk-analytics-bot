"""SQL analytics agent for aggregation queries."""

import logging
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session
import openai

from app.config import settings

logger = logging.getLogger(__name__)


class SQLAgent:
    """Convert natural language questions to SQL and execute analytics queries."""

    def __init__(self):
        """Initialize SQL agent."""
        self.client = openai.OpenAI(api_key=settings.openai_api_key)

    def answer_question(self, db: Session, question: str) -> Dict[str, Any]:
        """
        Answer an analytics question using SQL.

        Args:
            db: Database session
            question: Natural language question

        Returns:
            Answer dictionary with result, SQL, and evidence
        """
        logger.info(f"SQL Agent processing: {question}")

        # Generate SQL query from natural language
        sql_query, parameters = self._generate_sql(question)

        if not sql_query:
            return {
                "answer": "I couldn't generate a valid SQL query for that question.",
                "sql": None,
                "evidence": [],
                "error": "SQL generation failed"
            }

        logger.info(f"Generated SQL: {sql_query}")

        # Execute query
        try:
            result = db.execute(text(sql_query), parameters)
            rows = result.fetchall()

            # Format response
            answer = self._format_result(question, sql_query, rows)

            # Get evidence ticket IDs
            evidence = self._extract_evidence(db, question, parameters)

            return {
                "answer": answer["text"],
                "sql": sql_query,
                "evidence": evidence,
                "metadata": answer.get("metadata", {})
            }

        except Exception as e:
            logger.error(f"SQL execution error: {e}")
            return {
                "answer": f"Error executing query: {str(e)}",
                "sql": sql_query,
                "evidence": [],
                "error": str(e)
            }

    def _generate_sql(self, question: str) -> Tuple[Optional[str], Dict[str, Any]]:
        """
        Generate SQL query from natural language using LLM.

        Args:
            question: Natural language question

        Returns:
            Tuple of (SQL query string, parameters dict)
        """
        # Extract time parameters
        time_params = self._extract_time_filter(question)
        org_param = self._extract_organization(question)

        # Create prompt for LLM
        schema_context = """
        You are a SQL expert. Generate a PostgreSQL query for the following schema:

        Table: tickets
        Columns:
        - ticket_id (VARCHAR): Unique ticket identifier
        - subject (TEXT): Ticket subject
        - description (TEXT): Ticket description
        - organization_name (VARCHAR): Customer organization
        - requester_name (VARCHAR): Person who created the ticket
        - requester_email (VARCHAR): Requester's email
        - priority (VARCHAR): P1, P2, P3, P4, or null
        - status (VARCHAR): open, pending, solved, closed
        - tags (TEXT[]): Array of tags
        - created_at (TIMESTAMP): When ticket was created
        - updated_at (TIMESTAMP): Last update time
        - solved_at (TIMESTAMP): When ticket was solved
        - region (VARCHAR): EMEA, APAC, AMERICAS
        - issue_type (VARCHAR): Type of issue

        Important:
        - Use parameterized queries with :param_name syntax
        - For date filters, use created_at column
        - For organization searches, use ILIKE '%org_name%' for partial matching
        - For counting, use COUNT(*)
        - For aggregations by organization, use GROUP BY organization_name
        - Return only the SQL query, no explanations
        - Use proper PostgreSQL syntax
        """

        prompt = f"{schema_context}\n\nQuestion: {question}\n\nSQL Query:"

        try:
            response = self.client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {"role": "system", "content": "You are a SQL expert. Generate only valid PostgreSQL queries."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                max_tokens=500
            )

            sql_query = response.choices[0].message.content.strip()

            # Clean up the SQL (remove markdown code blocks if present)
            sql_query = re.sub(r"```sql\n?", "", sql_query)
            sql_query = re.sub(r"```\n?", "", sql_query)
            sql_query = sql_query.strip()

            # Inject time and org parameters
            parameters = {}
            if time_params:
                parameters.update(time_params)
            if org_param:
                parameters["org_name"] = f"%{org_param}%"

            return sql_query, parameters

        except Exception as e:
            logger.error(f"LLM SQL generation error: {e}")
            # Fallback to template-based SQL
            return self._generate_template_sql(question, time_params, org_param)

    def _generate_template_sql(
        self,
        question: str,
        time_params: Optional[Dict[str, datetime]],
        org_name: Optional[str]
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        """
        Generate SQL using templates as fallback.

        Args:
            question: Natural language question
            time_params: Time filter parameters
            org_name: Organization name

        Returns:
            Tuple of (SQL query, parameters)
        """
        q_lower = question.lower()
        parameters = {}

        # Build WHERE clause
        where_clauses = []

        if time_params:
            where_clauses.append("created_at >= :start_date")
            where_clauses.append("created_at <= :end_date")
            parameters.update(time_params)

        if org_name:
            where_clauses.append("organization_name ILIKE :org_name")
            parameters["org_name"] = f"%{org_name}%"

        where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

        # Detect query type
        if "how many" in q_lower or "count" in q_lower:
            # Count query
            sql = f"""
                SELECT COUNT(*) as count
                FROM tickets
                WHERE {where_clause}
            """

        elif "top" in q_lower or "most tickets" in q_lower:
            # Top organizations
            sql = f"""
                SELECT
                    organization_name,
                    COUNT(*) as ticket_count
                FROM tickets
                WHERE {where_clause}
                GROUP BY organization_name
                ORDER BY ticket_count DESC
                LIMIT 10
            """

        elif "priority" in q_lower and "breakdown" in q_lower:
            # Priority breakdown
            sql = f"""
                SELECT
                    priority,
                    COUNT(*) as count
                FROM tickets
                WHERE {where_clause}
                GROUP BY priority
                ORDER BY count DESC
            """

        else:
            # Generic count
            sql = f"""
                SELECT COUNT(*) as count
                FROM tickets
                WHERE {where_clause}
            """

        return sql, parameters

    def _extract_time_filter(self, question: str) -> Optional[Dict[str, datetime]]:
        """
        Extract time filter from question.

        Args:
            question: Natural language question

        Returns:
            Dictionary with start_date and end_date, or None
        """
        q_lower = question.lower()
        now = datetime.utcnow()

        # Last X days
        match = re.search(r"last (\d+) days?", q_lower)
        if match:
            days = int(match.group(1))
            return {
                "start_date": now - timedelta(days=days),
                "end_date": now
            }

        # Last month
        if "last month" in q_lower or "previous month" in q_lower:
            # First day of last month
            first_of_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if first_of_this_month.month == 1:
                first_of_last_month = first_of_this_month.replace(year=first_of_this_month.year - 1, month=12)
            else:
                first_of_last_month = first_of_this_month.replace(month=first_of_this_month.month - 1)

            return {
                "start_date": first_of_last_month,
                "end_date": first_of_this_month - timedelta(seconds=1)
            }

        # This month
        if "this month" in q_lower:
            first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            return {
                "start_date": first_of_month,
                "end_date": now
            }

        # Last week
        if "last week" in q_lower or "past week" in q_lower:
            return {
                "start_date": now - timedelta(days=7),
                "end_date": now
            }

        return None

    def _extract_organization(self, question: str) -> Optional[str]:
        """
        Extract organization name from question.

        Args:
            question: Natural language question

        Returns:
            Organization name or None
        """
        # Simple extraction - look for capitalized words that might be company names
        # This is a basic implementation; could be enhanced with NER
        common_org_patterns = [
            r"by ([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",  # "by Kixie"
            r"from ([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",  # "from Plivo"
            r"for ([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",  # "for BasalAnalytics"
        ]

        for pattern in common_org_patterns:
            match = re.search(pattern, question)
            if match:
                return match.group(1)

        return None

    def _format_result(
        self,
        question: str,
        sql: str,
        rows: List[Any]
    ) -> Dict[str, Any]:
        """
        Format SQL results into natural language answer.

        Args:
            question: Original question
            sql: SQL query executed
            rows: Query results

        Returns:
            Formatted answer dictionary
        """
        if not rows:
            return {
                "text": "No results found for that query.",
                "metadata": {"row_count": 0}
            }

        # Check result type
        if len(rows) == 1 and len(rows[0]) == 1:
            # Single value (e.g., COUNT)
            count = rows[0][0]
            return {
                "text": f"Found {count} tickets matching your criteria.",
                "metadata": {"count": count}
            }

        elif len(rows[0]) == 2:
            # Key-value pairs (e.g., GROUP BY results)
            lines = [f"• {row[0]}: {row[1]} tickets" for row in rows[:10]]
            text = "Results:\n" + "\n".join(lines)
            if len(rows) > 10:
                text += f"\n... and {len(rows) - 10} more"

            return {
                "text": text,
                "metadata": {"total_groups": len(rows)}
            }

        else:
            # Multiple columns
            return {
                "text": f"Found {len(rows)} results.",
                "metadata": {"row_count": len(rows)}
            }

    def _extract_evidence(
        self,
        db: Session,
        question: str,
        parameters: Dict[str, Any]
    ) -> List[str]:
        """
        Extract sample ticket IDs as evidence.

        Args:
            db: Database session
            question: Original question
            parameters: Query parameters

        Returns:
            List of ticket IDs
        """
        try:
            # Build simple query to get ticket IDs
            where_clauses = []
            if "start_date" in parameters:
                where_clauses.append("created_at >= :start_date")
                where_clauses.append("created_at <= :end_date")
            if "org_name" in parameters:
                where_clauses.append("organization_name ILIKE :org_name")

            where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

            sql = f"""
                SELECT ticket_id
                FROM tickets
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT 5
            """

            result = db.execute(text(sql), parameters)
            ticket_ids = [row[0] for row in result.fetchall()]
            return ticket_ids

        except Exception as e:
            logger.error(f"Error extracting evidence: {e}")
            return []
