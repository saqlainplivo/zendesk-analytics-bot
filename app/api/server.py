"""FastAPI server for Zendesk Analytics Chatbot."""

import logging
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

# Use Supabase-based services (works over HTTPS, bypasses firewall)
from app.database.supabase_db import get_db, check_db_connection, SupabaseDB
from app.services.analytics_service_supabase import AnalyticsService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Zendesk Analytics Chatbot API",
    description="LLM-powered analytics API for Zendesk support data",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
static_path = Path(__file__).parent.parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# Initialize services
analytics_service = AnalyticsService()


# Request/Response models
class ChatRequest(BaseModel):
    """Chat request model."""
    question: str = Field(..., min_length=1, description="Natural language question about tickets")


class ChatResponse(BaseModel):
    """Chat response model."""
    answer: str = Field(..., description="Answer to the question")
    evidence: List[str] = Field(default=[], description="Ticket IDs supporting the answer")
    query_type: str = Field(..., description="Type of query (sql or rag)")
    metadata: Dict[str, Any] = Field(default={}, description="Additional metadata")


class TicketResponse(BaseModel):
    """Ticket response model."""
    ticket_id: str
    subject: str
    description: Optional[str]
    organization_name: Optional[str]
    priority: Optional[str]
    status: Optional[str]
    created_at: Optional[str]


class StatsResponse(BaseModel):
    """Statistics response model."""
    total_tickets: int
    total_embeddings: int
    embedding_coverage: float
    status_distribution: Dict[str, int]
    priority_distribution: Dict[str, int]


# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check() -> Dict[str, str]:
    """
    Health check endpoint.

    Returns:
        Status dictionary
    """
    db_status = "healthy" if check_db_connection() else "unhealthy"

    return {
        "status": "healthy",
        "database": db_status
    }


# Chat endpoint
@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(
    request: ChatRequest,
    db: SupabaseDB = Depends(get_db)
) -> ChatResponse:
    """
    Ask a question about Zendesk tickets.

    The API will automatically route your question to the appropriate agent:
    - SQL Agent for aggregation queries (counts, top customers, etc.)
    - RAG Agent for semantic search (recent issues, summaries, etc.)

    Args:
        request: Chat request with question
        db: Database session

    Returns:
        Chat response with answer and evidence

    Example questions:
        - "How many tickets were raised by Kixie last month?"
        - "What issue did Kixie face recently?"
        - "Which organization generates the most tickets?"
        - "Summarize last week's support tickets"
    """
    start_time = time.time()

    try:
        # Get answer from analytics service
        result = analytics_service.answer_question(db, request.question)

        # Add execution time to metadata
        execution_time_ms = int((time.time() - start_time) * 1000)
        result["metadata"]["execution_time_ms"] = execution_time_ms

        return ChatResponse(**result)

    except Exception as e:
        logger.error(f"Chat endpoint error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing question: {str(e)}"
        )


# Ticket endpoints
@app.get("/tickets/{ticket_id}", response_model=TicketResponse, tags=["Tickets"])
async def get_ticket(
    ticket_id: str,
    db: SupabaseDB = Depends(get_db)
) -> TicketResponse:
    """
    Get a specific ticket by ID.

    Args:
        ticket_id: Ticket ID
        db: Supabase database instance

    Returns:
        Ticket details
    """
    ticket = db.get_ticket_by_id(ticket_id)

    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} not found"
        )

    return TicketResponse(**ticket)


@app.get("/tickets", response_model=List[TicketResponse], tags=["Tickets"])
async def get_recent_tickets(
    limit: int = 10,
    organization: Optional[str] = None,
    db: SupabaseDB = Depends(get_db)
) -> List[TicketResponse]:
    """
    Get recent tickets.

    Args:
        limit: Maximum number of tickets to return (default: 10)
        organization: Filter by organization name
        db: Supabase database instance

    Returns:
        List of recent tickets
    """
    filters = {"organization_name": organization} if organization else None
    tickets = db.execute_select_query(
        "tickets",
        columns="ticket_id,subject,description,organization_name,priority,status,created_at",
        filters=filters,
        order_by="-created_at",
        limit=limit
    )
    return [TicketResponse(**t) for t in tickets]


# Stats endpoint (simplified for Supabase)
@app.get("/stats", tags=["Statistics"])
async def get_stats(db: SupabaseDB = Depends(get_db)) -> Dict[str, Any]:
    """
    Get overall ticket statistics.

    Args:
        db: Supabase database instance

    Returns:
        Statistics about tickets and embeddings
    """
    total_tickets = db.execute_count_query("tickets")

    return {
        "total_tickets": total_tickets,
        "message": "Full stats require additional RPC functions in Supabase"
    }


# Frontend endpoint
@app.get("/", tags=["Root"])
async def root():
    """
    Serve the frontend application.
    """
    static_path = Path(__file__).parent.parent / "static" / "index.html"
    if static_path.exists():
        return FileResponse(str(static_path))
    return {
        "message": "Zendesk Analytics Chatbot API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


# API info endpoint
@app.get("/api", tags=["Root"])
async def api_info() -> Dict[str, str]:
    """
    API information endpoint.

    Returns:
        Welcome message and API info
    """
    return {
        "message": "Zendesk Analytics Chatbot API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.api.server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
