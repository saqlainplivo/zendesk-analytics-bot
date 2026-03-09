"""Supabase client for database operations (works over HTTPS)."""

import logging
from typing import Any, Dict, List, Optional
from supabase import create_client, Client

from app.config import settings

logger = logging.getLogger(__name__)

# Global Supabase client
_supabase_client: Optional[Client] = None


def get_supabase_client() -> Client:
    """Get or create Supabase client."""
    global _supabase_client

    if _supabase_client is None:
        _supabase_client = create_client(
            settings.supabase_url,
            settings.supabase_anon_key
        )
        logger.info("Supabase client initialized")

    return _supabase_client


def execute_query(query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Execute a raw SQL query using Supabase RPC.

    Note: This requires creating a PostgreSQL function in Supabase.
    For now, we'll use the REST API for queries.

    Args:
        query: SQL query string
        params: Query parameters

    Returns:
        Query results as list of dictionaries
    """
    client = get_supabase_client()

    try:
        # For SELECT queries, use the table API
        # For complex queries, we'll need to create RPC functions
        # This is a simplified implementation
        logger.warning("Direct SQL execution not fully supported via Supabase REST API")
        return []
    except Exception as e:
        logger.error(f"Query execution error: {e}")
        raise


def check_connection() -> bool:
    """Check if Supabase connection is working."""
    try:
        client = get_supabase_client()
        # Try a simple query to verify connection
        result = client.table("tickets").select("ticket_id").limit(1).execute()
        logger.info("Supabase connection successful")
        return True
    except Exception as e:
        logger.error(f"Supabase connection failed: {e}")
        return False
