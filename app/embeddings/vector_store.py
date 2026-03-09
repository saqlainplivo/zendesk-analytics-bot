"""Vector store operations using pgvector."""

import logging
from typing import List, Dict, Any, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database.models import Ticket, TicketEmbedding, Comment
from app.embeddings.embedder import Embedder
from app.config import settings

logger = logging.getLogger(__name__)


class VectorStore:
    """Manage ticket embeddings in pgvector."""

    def __init__(self, embedder: Optional[Embedder] = None):
        """
        Initialize vector store.

        Args:
            embedder: Embedder instance (creates one if not provided)
        """
        self.embedder = embedder or Embedder()

    def generate_and_store_embedding(
        self,
        db: Session,
        ticket_id: str
    ) -> bool:
        """
        Generate and store embedding for a single ticket.

        Args:
            db: Database session
            ticket_id: Ticket ID

        Returns:
            True if successful, False otherwise
        """
        try:
            # Fetch ticket with comments
            ticket = db.query(Ticket).filter(Ticket.ticket_id == ticket_id).first()

            if not ticket:
                logger.warning(f"Ticket {ticket_id} not found")
                return False

            # Get comments
            comments = db.query(Comment).filter(Comment.ticket_id == ticket_id).all()
            comment_texts = [c.body for c in comments if c.body]

            # Generate embedding
            embedding_vector = self.embedder.embed_ticket(
                subject=ticket.subject,
                description=ticket.description,
                comments=comment_texts
            )

            # Get content text
            content = self.embedder.get_ticket_content_for_embedding(
                subject=ticket.subject,
                description=ticket.description,
                comments=comment_texts
            )

            # Store embedding (upsert)
            existing = db.query(TicketEmbedding).filter(
                TicketEmbedding.ticket_id == ticket_id
            ).first()

            if existing:
                existing.embedding = embedding_vector
                existing.content = content
                existing.embedding_model = self.embedder.model
            else:
                embedding_record = TicketEmbedding(
                    ticket_id=ticket_id,
                    embedding=embedding_vector,
                    content=content,
                    embedding_model=self.embedder.model
                )
                db.add(embedding_record)

            db.commit()
            logger.debug(f"Stored embedding for ticket {ticket_id}")
            return True

        except Exception as e:
            db.rollback()
            logger.error(f"Failed to generate/store embedding for {ticket_id}: {e}")
            return False

    def generate_embeddings_batch(
        self,
        db: Session,
        ticket_ids: Optional[List[str]] = None,
        batch_size: int = 50
    ) -> Dict[str, int]:
        """
        Generate embeddings for multiple tickets in batches.

        Args:
            db: Database session
            ticket_ids: List of specific ticket IDs (if None, processes all tickets without embeddings)
            batch_size: Number of tickets to process per batch

        Returns:
            Statistics dict with counts
        """
        stats = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0
        }

        # Get tickets to process
        if ticket_ids:
            query = db.query(Ticket).filter(Ticket.ticket_id.in_(ticket_ids))
        else:
            # Get tickets without embeddings
            query = db.query(Ticket).outerjoin(TicketEmbedding).filter(
                TicketEmbedding.id.is_(None)
            )

        tickets = query.all()
        stats["total"] = len(tickets)

        logger.info(f"Processing {stats['total']} tickets for embeddings")

        # Process in batches
        for i in range(0, len(tickets), batch_size):
            batch = tickets[i:i + batch_size]

            for ticket in batch:
                success = self.generate_and_store_embedding(db, ticket.ticket_id)
                if success:
                    stats["success"] += 1
                else:
                    stats["failed"] += 1

            logger.info(
                f"Batch {i//batch_size + 1} complete: "
                f"{stats['success']} success, {stats['failed']} failed"
            )

        logger.info(f"Embedding generation complete: {stats}")
        return stats

    def search_similar_tickets(
        self,
        db: Session,
        query_text: str,
        top_k: int = None,
        similarity_threshold: float = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar tickets using semantic similarity.

        Args:
            db: Database session
            query_text: Search query
            top_k: Number of results to return
            similarity_threshold: Minimum similarity score (0-1)

        Returns:
            List of similar tickets with metadata
        """
        top_k = top_k or settings.top_k_results
        similarity_threshold = similarity_threshold or settings.similarity_threshold

        # Generate query embedding
        query_embedding = self.embedder.embed_text(query_text)

        # Search using pgvector function
        sql = text("""
            SELECT
                t.ticket_id,
                t.subject,
                t.description,
                t.organization_name,
                t.priority,
                t.status,
                t.created_at,
                te.content,
                1 - (te.embedding <=> :query_embedding::vector) as similarity
            FROM ticket_embeddings te
            JOIN tickets t ON t.ticket_id = te.ticket_id
            WHERE 1 - (te.embedding <=> :query_embedding::vector) > :threshold
            ORDER BY te.embedding <=> :query_embedding::vector
            LIMIT :limit
        """)

        result = db.execute(
            sql,
            {
                "query_embedding": query_embedding,
                "threshold": similarity_threshold,
                "limit": top_k
            }
        )

        tickets = []
        for row in result:
            tickets.append({
                "ticket_id": row.ticket_id,
                "subject": row.subject,
                "description": row.description,
                "organization_name": row.organization_name,
                "priority": row.priority,
                "status": row.status,
                "created_at": row.created_at,
                "content": row.content,
                "similarity": float(row.similarity)
            })

        logger.info(f"Found {len(tickets)} similar tickets for query")
        return tickets

    def get_embedding_stats(self, db: Session) -> Dict[str, Any]:
        """
        Get statistics about embeddings in the database.

        Args:
            db: Database session

        Returns:
            Statistics dictionary
        """
        total_tickets = db.query(Ticket).count()
        total_embeddings = db.query(TicketEmbedding).count()
        missing_embeddings = total_tickets - total_embeddings

        return {
            "total_tickets": total_tickets,
            "total_embeddings": total_embeddings,
            "missing_embeddings": missing_embeddings,
            "coverage_percent": (total_embeddings / total_tickets * 100) if total_tickets > 0 else 0
        }
