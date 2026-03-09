"""RAG agent for semantic ticket search and summarization."""

import logging
from typing import Dict, Any, List

from sqlalchemy.orm import Session
import openai

from app.embeddings.vector_store import VectorStore
from app.config import settings

logger = logging.getLogger(__name__)


class RAGAgent:
    """Retrieve and Generate agent for ticket investigation and summarization."""

    def __init__(self, vector_store: VectorStore = None):
        """
        Initialize RAG agent.

        Args:
            vector_store: VectorStore instance
        """
        self.vector_store = vector_store or VectorStore()
        self.client = openai.OpenAI(api_key=settings.openai_api_key)

    def answer_question(
        self,
        db: Session,
        question: str,
        top_k: int = None
    ) -> Dict[str, Any]:
        """
        Answer a question using semantic search and LLM generation.

        Args:
            db: Database session
            question: Natural language question
            top_k: Number of similar tickets to retrieve

        Returns:
            Answer dictionary with response and evidence
        """
        logger.info(f"RAG Agent processing: {question}")

        top_k = top_k or settings.top_k_results

        # Step 1: Retrieve similar tickets
        similar_tickets = self.vector_store.search_similar_tickets(
            db=db,
            query_text=question,
            top_k=top_k
        )

        if not similar_tickets:
            return {
                "answer": "I couldn't find any relevant tickets for that question.",
                "evidence": [],
                "metadata": {"retrieved_count": 0}
            }

        logger.info(f"Retrieved {len(similar_tickets)} similar tickets")

        # Step 2: Generate answer using LLM
        answer = self._generate_answer(question, similar_tickets)

        # Step 3: Extract evidence
        evidence = [ticket["ticket_id"] for ticket in similar_tickets]

        return {
            "answer": answer,
            "evidence": evidence,
            "metadata": {
                "retrieved_count": len(similar_tickets),
                "tickets": similar_tickets
            }
        }

    def _generate_answer(
        self,
        question: str,
        tickets: List[Dict[str, Any]]
    ) -> str:
        """
        Generate answer from retrieved tickets using LLM.

        Args:
            question: User question
            tickets: List of similar tickets

        Returns:
            Generated answer
        """
        # Build context from tickets
        context_parts = []
        for i, ticket in enumerate(tickets, 1):
            context_parts.append(
                f"Ticket #{i} (ID: {ticket['ticket_id']}):\n"
                f"Organization: {ticket['organization_name']}\n"
                f"Subject: {ticket['subject']}\n"
                f"Priority: {ticket['priority']}\n"
                f"Status: {ticket['status']}\n"
                f"Created: {ticket['created_at']}\n"
                f"Content: {ticket['content'][:500]}...\n"
                f"Similarity: {ticket['similarity']:.2f}\n"
            )

        context = "\n---\n".join(context_parts)

        # Create prompt
        system_prompt = """You are a helpful customer support analyst.
        Answer questions about Zendesk tickets based on the provided context.

        Guidelines:
        - Be concise and specific
        - Always cite ticket IDs when referencing specific issues
        - If asked about recent issues, focus on the most relevant tickets
        - If asked to summarize, provide a clear summary with key points
        - If the context doesn't contain enough information, say so
        """

        user_prompt = f"""Question: {question}

Relevant Tickets:
{context}

Please provide a clear and concise answer, citing specific ticket IDs when relevant."""

        try:
            response = self.client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=settings.llm_temperature,
                max_tokens=1000
            )

            answer = response.choices[0].message.content.strip()
            return answer

        except Exception as e:
            logger.error(f"LLM generation error: {e}")
            # Fallback to simple summary
            return self._generate_fallback_answer(question, tickets)

    def _generate_fallback_answer(
        self,
        question: str,
        tickets: List[Dict[str, Any]]
    ) -> str:
        """
        Generate simple fallback answer without LLM.

        Args:
            question: User question
            tickets: List of similar tickets

        Returns:
            Fallback answer
        """
        if not tickets:
            return "No relevant tickets found."

        # Simple summary
        ticket = tickets[0]
        return (
            f"Most relevant ticket (ID: {ticket['ticket_id']}):\n"
            f"Organization: {ticket['organization_name']}\n"
            f"Subject: {ticket['subject']}\n"
            f"Priority: {ticket['priority']}\n"
            f"Status: {ticket['status']}\n"
            f"Created: {ticket['created_at']}\n\n"
            f"Found {len(tickets)} similar tickets total."
        )

    def summarize_tickets(
        self,
        db: Session,
        organization: str = None,
        time_period: str = None,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Summarize recent tickets, optionally filtered by organization or time.

        Args:
            db: Database session
            organization: Organization name filter
            time_period: Time period (e.g., "last week")
            limit: Number of tickets to include

        Returns:
            Summary dictionary
        """
        # Build search query
        query_parts = ["Recent support tickets"]
        if organization:
            query_parts.append(f"from {organization}")
        if time_period:
            query_parts.append(f"{time_period}")

        query = " ".join(query_parts)

        # Retrieve tickets
        similar_tickets = self.vector_store.search_similar_tickets(
            db=db,
            query_text=query,
            top_k=limit,
            similarity_threshold=0.0  # Get all, we'll sort by date
        )

        if not similar_tickets:
            return {
                "answer": "No tickets found matching the criteria.",
                "evidence": [],
                "metadata": {"ticket_count": 0}
            }

        # Generate summary
        summary = self._generate_summary(similar_tickets, organization, time_period)

        evidence = [ticket["ticket_id"] for ticket in similar_tickets]

        return {
            "answer": summary,
            "evidence": evidence,
            "metadata": {
                "ticket_count": len(similar_tickets),
                "tickets": similar_tickets
            }
        }

    def _generate_summary(
        self,
        tickets: List[Dict[str, Any]],
        organization: str = None,
        time_period: str = None
    ) -> str:
        """
        Generate summary of tickets.

        Args:
            tickets: List of tickets
            organization: Organization filter
            time_period: Time period

        Returns:
            Summary text
        """
        # Build context
        context_parts = []
        for ticket in tickets:
            context_parts.append(
                f"- {ticket['subject']} (ID: {ticket['ticket_id']}, "
                f"Priority: {ticket['priority']}, Status: {ticket['status']})"
            )

        context = "\n".join(context_parts)

        # Create prompt
        filter_desc = ""
        if organization:
            filter_desc += f" from {organization}"
        if time_period:
            filter_desc += f" {time_period}"

        prompt = f"""Summarize the following support tickets{filter_desc}:

{context}

Provide a brief summary highlighting:
1. Total number of tickets
2. Common themes or patterns
3. Priority distribution
4. Any critical issues (P1/P2)"""

        try:
            response = self.client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {"role": "system", "content": "You are a support analyst creating concise ticket summaries."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=500
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"Summary generation error: {e}")
            # Fallback
            return (
                f"Found {len(tickets)} tickets{filter_desc}.\n"
                f"Most recent: {tickets[0]['subject']} (ID: {tickets[0]['ticket_id']})"
            )
