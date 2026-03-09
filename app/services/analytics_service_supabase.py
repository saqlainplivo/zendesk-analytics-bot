"""Analytics service using Supabase REST API."""

import logging
from typing import Dict, Any

from app.agents.router_agent_supabase import RouterAgent
from app.database.supabase_db import SupabaseDB

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Service for answering questions about Zendesk tickets using Supabase."""

    def __init__(self):
        """Initialize analytics service."""
        self.router = RouterAgent()

    def answer_question(
        self,
        db: SupabaseDB,
        question: str
    ) -> Dict[str, Any]:
        """
        Answer a natural language question about tickets.

        Args:
            db: Supabase database instance
            question: Natural language question

        Returns:
            Answer dictionary with response, evidence, and metadata
        """
        logger.info(f"Processing question: {question}")

        try:
            # Route and answer using appropriate agent
            result = self.router.route_and_answer(db, question)

            logger.info(f"Answer generated using {result['query_type']} agent")

            return result

        except Exception as e:
            logger.error(f"Error answering question: {e}", exc_info=True)
            return {
                "answer": f"Sorry, I encountered an error processing your question: {str(e)}",
                "evidence": [],
                "query_type": "error",
                "metadata": {"error": str(e)}
            }
