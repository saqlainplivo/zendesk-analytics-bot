"""Router agent with reasoning engine for better query understanding."""

import logging
from typing import Dict, Any

from app.agents.sql_agent_supabase import SQLAgent
from app.agents.rag_agent_supabase import RAGAgent
from app.agents.reasoning_engine import ReasoningEngine
from app.database.supabase_db import SupabaseDB

logger = logging.getLogger(__name__)


class RouterAgent:
    """Router agent with reasoning engine for intelligent query routing."""

    def __init__(self):
        """Initialize router with reasoning engine and specialized agents."""
        self.reasoning_engine = ReasoningEngine()
        self.sql_agent = SQLAgent()
        self.rag_agent = RAGAgent()

    def route_and_answer(
        self,
        db: SupabaseDB,
        question: str
    ) -> Dict[str, Any]:
        """
        Route question using reasoning engine, then get answer.

        Args:
            db: Supabase database instance
            question: Natural language question

        Returns:
            Answer dictionary with reasoning, response, and evidence
        """
        logger.info(f"🧠 Routing question with reasoning: {question}")

        # Step 1: Analyze question with reasoning engine
        analysis = self.reasoning_engine.analyze_question(question)

        # Step 2: Create execution plan
        plan = self.reasoning_engine.create_execution_plan(question, analysis)

        # Extract parameters from analysis
        organization = analysis.get("organization")
        query_type = analysis.get("query_type", "analytics")

        logger.info(f"📋 Plan: {plan['reasoning']}")
        logger.info(f"🎯 Organization: {organization}")
        logger.info(f"🔀 Query type: {query_type}")

        # Step 3: Execute query with appropriate agent
        # Override the question with enhanced version if we have filters
        enhanced_question = question
        if organization and organization.lower() not in question.lower():
            enhanced_question = f"{question} (filtering by organization: {organization})"

        if query_type == "analytics":
            # Use SQL agent with extracted parameters
            logger.info("📊 Using SQL Analytics Agent")
            result = self._execute_sql_query(db, question, organization, analysis)
        else:
            # Use RAG agent
            logger.info("🔍 Using Semantic Search Agent")
            result = self.rag_agent.answer_question(db, enhanced_question)

        # Step 4: Add reasoning to result
        result["reasoning"] = plan["reasoning"]
        result["query_type"] = "analytics" if query_type == "analytics" else "lookup"

        return result

    def _execute_sql_query(
        self,
        db: SupabaseDB,
        question: str,
        organization: str,
        analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute SQL query with enhanced organization filtering."""
        intent = analysis.get("intent", "count")

        # Direct database query based on intent
        if intent == "count":
            return self._handle_count_with_org(db, question, organization)
        elif intent == "top_n":
            return self.sql_agent.answer_question(db, question)
        else:
            return self.sql_agent.answer_question(db, question)

    def _handle_count_with_org(
        self,
        db: SupabaseDB,
        question: str,
        organization: str
    ) -> Dict[str, Any]:
        """Handle count queries with explicit organization filtering."""
        if not organization:
            # No organization filter
            count = db.execute_count_query("tickets")
            tickets = db.execute_select_query(
                "tickets",
                columns="ticket_id,subject,organization_name,priority,status,created_at,description",
                order_by="-created_at",
                limit=5
            )
        else:
            # First try exact match
            filters = {"organization_name": organization}
            count = db.execute_count_query("tickets", filters)

            if count == 0:
                # Try case-insensitive search
                all_tickets = db.execute_select_query(
                    "tickets",
                    columns="ticket_id,subject,organization_name,priority,status,created_at,description",
                    order_by="-created_at",
                    limit=5000  # Get more for filtering
                )

                org_lower = organization.lower()
                matching_tickets = [
                    t for t in all_tickets
                    if t.get('organization_name', '').lower() == org_lower or
                       org_lower in t.get('organization_name', '').lower()
                ]

                count = len(matching_tickets)
                tickets = matching_tickets[:5]
            else:
                tickets = db.execute_select_query(
                    "tickets",
                    columns="ticket_id,subject,organization_name,priority,status,created_at,description",
                    filters=filters,
                    order_by="-created_at",
                    limit=5
                )

        evidence = [t["ticket_id"] for t in tickets]

        # Generate answer
        answer = f"Found {count} ticket{'s' if count != 1 else ''}"
        if organization:
            answer += f" for **{organization}**"
        answer += "."

        if count > 0 and tickets:
            answer += f"\n\n**Most recent:**\n"
            for i, t in enumerate(tickets[:3], 1):
                answer += f"{i}. {t.get('subject', 'N/A')} (#{t['ticket_id']})\n"

        return {
            "answer": answer,
            "evidence": evidence,
            "evidence_details": tickets,
            "metadata": {
                "count": count,
                "organization": organization,
                "query_type": "count"
            }
        }
