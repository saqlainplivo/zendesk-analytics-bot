"""Analytics service - business logic layer."""

import logging
from typing import Dict, Any

from sqlalchemy.orm import Session

from app.agents.router_agent import RouterAgent

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Service for handling analytics queries."""

    def __init__(self):
        """Initialize analytics service."""
        self.router = RouterAgent()

    def answer_question(self, db: Session, question: str) -> Dict[str, Any]:
        """
        Answer a question about Zendesk tickets.

        Args:
            db: Database session
            question: Natural language question

        Returns:
            Answer dictionary with result and metadata
        """
        try:
            result = self.router.route_and_answer(db, question)
            return result

        except Exception as e:
            logger.error(f"Error answering question: {e}")
            return {
                "answer": f"Sorry, I encountered an error processing your question: {str(e)}",
                "evidence": [],
                "query_type": "error",
                "error": str(e)
            }
