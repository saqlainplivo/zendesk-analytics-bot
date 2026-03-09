"""Ticket service - business logic for ticket operations."""

import logging
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database.models import Ticket, TicketEmbedding

logger = logging.getLogger(__name__)


class TicketService:
    """Service for ticket-related operations."""

    def get_ticket_by_id(self, db: Session, ticket_id: str) -> Optional[Dict[str, Any]]:
        """
        Get ticket by ID.

        Args:
            db: Database session
            ticket_id: Ticket ID

        Returns:
            Ticket dictionary or None
        """
        ticket = db.query(Ticket).filter(Ticket.ticket_id == ticket_id).first()

        if not ticket:
            return None

        return {
            "ticket_id": ticket.ticket_id,
            "subject": ticket.subject,
            "description": ticket.description,
            "organization_name": ticket.organization_name,
            "requester_name": ticket.requester_name,
            "requester_email": ticket.requester_email,
            "priority": ticket.priority,
            "status": ticket.status,
            "tags": ticket.tags,
            "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
            "updated_at": ticket.updated_at.isoformat() if ticket.updated_at else None,
        }

    def get_recent_tickets(
        self,
        db: Session,
        limit: int = 10,
        organization: str = None
    ) -> List[Dict[str, Any]]:
        """
        Get recent tickets.

        Args:
            db: Database session
            limit: Number of tickets to return
            organization: Filter by organization

        Returns:
            List of ticket dictionaries
        """
        query = db.query(Ticket)

        if organization:
            query = query.filter(Ticket.organization_name.ilike(f"%{organization}%"))

        tickets = query.order_by(desc(Ticket.created_at)).limit(limit).all()

        return [
            {
                "ticket_id": t.ticket_id,
                "subject": t.subject,
                "organization_name": t.organization_name,
                "priority": t.priority,
                "status": t.status,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in tickets
        ]

    def get_ticket_stats(self, db: Session) -> Dict[str, Any]:
        """
        Get overall ticket statistics.

        Args:
            db: Database session

        Returns:
            Statistics dictionary
        """
        total_tickets = db.query(Ticket).count()
        total_embeddings = db.query(TicketEmbedding).count()

        # Count by status
        from sqlalchemy import func
        status_counts = db.query(
            Ticket.status,
            func.count(Ticket.ticket_id)
        ).group_by(Ticket.status).all()

        status_distribution = {status: count for status, count in status_counts}

        # Count by priority
        priority_counts = db.query(
            Ticket.priority,
            func.count(Ticket.ticket_id)
        ).group_by(Ticket.priority).all()

        priority_distribution = {
            priority or "None": count for priority, count in priority_counts
        }

        return {
            "total_tickets": total_tickets,
            "total_embeddings": total_embeddings,
            "embedding_coverage": (total_embeddings / total_tickets * 100) if total_tickets > 0 else 0,
            "status_distribution": status_distribution,
            "priority_distribution": priority_distribution,
        }
