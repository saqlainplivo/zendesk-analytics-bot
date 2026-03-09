"""RAG agent using Supabase REST API."""

import logging
from typing import Dict, Any, List
import openai

from app.database.supabase_db import SupabaseDB
from app.embeddings.embedder import Embedder
from app.config import settings

logger = logging.getLogger(__name__)


class RAGAgent:
    """Retrieve and Generate agent for ticket investigation using Supabase."""

    def __init__(self):
        """Initialize RAG agent."""
        self.embedder = Embedder()
        self.client = openai.OpenAI(api_key=settings.openai_api_key)

    def answer_question(
        self,
        db: SupabaseDB,
        question: str,
        top_k: int = None
    ) -> Dict[str, Any]:
        """
        Answer a question using semantic search and LLM generation.

        Args:
            db: Supabase database instance
            question: Natural language question
            top_k: Number of similar tickets to retrieve

        Returns:
            Answer dictionary with response and evidence
        """
        logger.info(f"RAG Agent processing: {question}")

        top_k = top_k or settings.top_k_results

        # Step 1: Generate query embedding
        query_embedding = self.embedder.embed_text(question)

        # Step 2: Retrieve similar tickets
        similar_tickets = db.search_similar_tickets(
            query_embedding=query_embedding,
            top_k=top_k,
            threshold=settings.similarity_threshold
        )

        if not similar_tickets:
            return {
                "answer": "I couldn't find any relevant tickets for that question.",
                "evidence": [],
                "metadata": {"retrieved_count": 0}
            }

        logger.info(f"Retrieved {len(similar_tickets)} similar tickets")

        # Step 3: Generate answer using LLM
        answer = self._generate_answer(question, similar_tickets)

        # Step 4: Extract evidence
        evidence = [ticket["ticket_id"] for ticket in similar_tickets]

        return {
            "answer": answer,
            "evidence": evidence,
            "evidence_details": similar_tickets,  # Full ticket details for preview
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
        """Generate answer from retrieved tickets using LLM."""
        # Build context from tickets
        context_parts = []
        for i, ticket in enumerate(tickets, 1):
            context_parts.append(
                f"Ticket #{i} (ID: {ticket.get('ticket_id', 'N/A')}):\n"
                f"Organization: {ticket.get('organization_name', 'N/A')}\n"
                f"Subject: {ticket.get('subject', 'N/A')}\n"
                f"Description: {ticket.get('description', 'N/A')[:300]}...\n"
                f"Created: {ticket.get('created_at', 'N/A')}\n"
                f"Similarity: {ticket.get('similarity', 0):.2f}\n"
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
        """Generate simple fallback answer without LLM."""
        if not tickets:
            return "No relevant tickets found."

        # Simple summary
        ticket = tickets[0]
        return (
            f"Most relevant ticket (ID: {ticket.get('ticket_id', 'N/A')}):\n"
            f"Organization: {ticket.get('organization_name', 'N/A')}\n"
            f"Subject: {ticket.get('subject', 'N/A')}\n"
            f"Created: {ticket.get('created_at', 'N/A')}\n\n"
            f"Found {len(tickets)} similar tickets total."
        )
