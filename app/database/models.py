"""SQLAlchemy ORM models."""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Column, String, Text, DateTime, Date, Boolean, Integer,
    ForeignKey, ARRAY, func
)
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from app.database.db import Base


class Ticket(Base):
    """Ticket model."""

    __tablename__ = "tickets"

    ticket_id = Column(String(50), primary_key=True)
    subject = Column(Text, nullable=False)
    description = Column(Text)
    organization_name = Column(String(255))
    requester_name = Column(String(255))
    requester_email = Column(String(255))
    requester_domain = Column(String(255))
    assignee = Column(String(255))
    assignee_email = Column(String(255))
    priority = Column(String(50))
    status = Column(String(50))
    ticket_type = Column(String(50))
    group_name = Column(String(255))
    tags = Column(ARRAY(Text))
    product = Column(String(100))
    issue_type = Column(String(100))
    region = Column(String(100))
    country = Column(String(100))
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True))
    solved_at = Column(DateTime(timezone=True))
    via_channel = Column(String(50))
    satisfaction_score = Column(String(50))

    # Relationships
    comments = relationship("Comment", back_populates="ticket", cascade="all, delete-orphan")
    embedding = relationship("TicketEmbedding", back_populates="ticket", uselist=False, cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Ticket {self.ticket_id}: {self.subject[:50]}>"


class Comment(Base):
    """Comment model."""

    __tablename__ = "comments"

    comment_id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_id = Column(String(50), ForeignKey("tickets.ticket_id", ondelete="CASCADE"), nullable=False)
    author = Column(String(255))
    author_email = Column(String(255))
    body = Column(Text)
    is_public = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False)

    # Relationships
    ticket = relationship("Ticket", back_populates="comments")

    def __repr__(self) -> str:
        return f"<Comment {self.comment_id} for Ticket {self.ticket_id}>"


class TicketEmbedding(Base):
    """Ticket embedding model for semantic search."""

    __tablename__ = "ticket_embeddings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_id = Column(String(50), ForeignKey("tickets.ticket_id", ondelete="CASCADE"), unique=True, nullable=False)
    embedding = Column(Vector(1536), nullable=False)
    content = Column(Text, nullable=False)
    embedding_model = Column(String(100), nullable=False, default="text-embedding-3-small")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    ticket = relationship("Ticket", back_populates="embedding")

    def __repr__(self) -> str:
        return f"<TicketEmbedding for {self.ticket_id}>"
