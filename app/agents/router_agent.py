"""Router agent to classify queries and route to appropriate agent."""

import logging
import re
from enum import Enum
from typing import Dict, Any

from sqlalchemy.orm import Session
import openai

from app.agents.sql_agent import SQLAgent
from app.agents.rag_agent import RAGAgent
from app.config import settings

logger = logging.getLogger(__name__)


class QueryType(str, Enum):
    """Types of queries the router can handle."""
    ANALYTICS = "analytics"  # SQL-based aggregation/counting
    TICKET_LOOKUP = "ticket_lookup"  # Semantic search for specific tickets
    SUMMARY = "summary"  # Summarize tickets
    TREND = "trend"  # Trend analysis (can use SQL or RAG)


class RouterAgent:
    """Route queries to the appropriate specialized agent."""

    # Keywords that indicate SQL analytics queries
    ANALYTICS_KEYWORDS = [
        "how many",
        "count",
        "total",
        "number of",
        "average",
        "top",
        "most",
        "least",
        "percentage",
        "breakdown",
        "distribution",
        "which organization",
        "which customer",
        "which companies",
    ]

    # Keywords that indicate RAG/semantic search queries
    LOOKUP_KEYWORDS = [
        "what issue",
        "what problem",
        "describe",
        "explain",
        "tell me about",
        "recent issue",
        "recent problem",
        "last ticket",
        "latest ticket",
        "recent ticket",
    ]

    # Keywords for summarization
    SUMMARY_KEYWORDS = [
        "summarize",
        "summary of",
        "overview of",
        "brief",
        "recap",
    ]

    # Keywords for contact lookup (can use SQL or RAG)
    CONTACT_KEYWORDS = [
        "contact",
        "point of contact",
        "poc",
        "who is",
        "requester",
    ]

    def __init__(self):
        """Initialize router agent."""
        self.sql_agent = SQLAgent()
        self.rag_agent = RAGAgent()
        self.client = openai.OpenAI(api_key=settings.openai_api_key)

    def route_and_answer(self, db: Session, question: str) -> Dict[str, Any]:
        """
        Route question to appropriate agent and return answer.

        Args:
            db: Database session
            question: User question

        Returns:
            Answer dictionary with result and metadata
        """
        logger.info(f"Router processing question: {question}")

        # Classify query type
        query_type = self._classify_query(question)
        logger.info(f"Classified as: {query_type}")

        # Route to appropriate agent
        if query_type == QueryType.ANALYTICS:
            result = self.sql_agent.answer_question(db, question)
            result["query_type"] = "sql"

        elif query_type == QueryType.TICKET_LOOKUP:
            result = self.rag_agent.answer_question(db, question)
            result["query_type"] = "rag"

        elif query_type == QueryType.SUMMARY:
            result = self.rag_agent.answer_question(db, question)
            result["query_type"] = "rag"

        else:
            # Default to RAG for unclear queries
            result = self.rag_agent.answer_question(db, question)
            result["query_type"] = "rag"

        return result

    def _classify_query(self, question: str) -> QueryType:
        """
        Classify query type using rule-based approach.

        Args:
            question: User question

        Returns:
            QueryType enum
        """
        q_lower = question.lower()

        # Check for analytics keywords (highest priority)
        for keyword in self.ANALYTICS_KEYWORDS:
            if keyword in q_lower:
                return QueryType.ANALYTICS

        # Check for summary keywords
        for keyword in self.SUMMARY_KEYWORDS:
            if keyword in q_lower:
                return QueryType.SUMMARY

        # Check for lookup keywords
        for keyword in self.LOOKUP_KEYWORDS:
            if keyword in q_lower:
                return QueryType.TICKET_LOOKUP

        # Check for contact keywords (use SQL for efficiency)
        for keyword in self.CONTACT_KEYWORDS:
            if keyword in q_lower:
                # Contact queries are often answered better with SQL
                return QueryType.ANALYTICS

        # Default to ticket lookup (RAG) for open-ended questions
        return QueryType.TICKET_LOOKUP

    def _classify_query_with_llm(self, question: str) -> QueryType:
        """
        Classify query using LLM (more accurate but slower).

        This can be used as an alternative to rule-based classification.

        Args:
            question: User question

        Returns:
            QueryType enum
        """
        prompt = f"""Classify the following question into one of these categories:

1. ANALYTICS: Questions about counts, totals, averages, top/most, trends, breakdowns
   Examples: "How many tickets?", "Which organization has the most?", "Top issues?"

2. TICKET_LOOKUP: Questions about specific ticket content, issues, problems
   Examples: "What issue did X face?", "Recent problem from Y?", "Last ticket about Z?"

3. SUMMARY: Questions asking for summaries or overviews
   Examples: "Summarize last week's tickets", "Overview of issues from X"

Question: {question}

Reply with only one word: ANALYTICS, TICKET_LOOKUP, or SUMMARY"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",  # Use faster model for classification
                messages=[
                    {"role": "system", "content": "You are a query classifier."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                max_tokens=10
            )

            classification = response.choices[0].message.content.strip().upper()

            if "ANALYTICS" in classification:
                return QueryType.ANALYTICS
            elif "TICKET_LOOKUP" in classification:
                return QueryType.TICKET_LOOKUP
            elif "SUMMARY" in classification:
                return QueryType.SUMMARY
            else:
                return QueryType.TICKET_LOOKUP  # Default

        except Exception as e:
            logger.error(f"LLM classification error: {e}")
            # Fallback to rule-based
            return self._classify_query(question)
