"""Database wrapper that uses Supabase client (works over HTTPS, bypasses firewall)."""

import logging
from typing import Any, Dict, List, Optional, Generator
from supabase import create_client, Client
from app.config import settings

logger = logging.getLogger(__name__)

# Global Supabase client
_client: Optional[Client] = None


def get_supabase() -> Client:
    """Get or create Supabase client."""
    global _client
    if _client is None:
        _client = create_client(
            settings.supabase_url,
            settings.supabase_anon_key
        )
    return _client


class SupabaseSession:
    """Mock session object that uses Supabase client."""

    def __init__(self):
        self.client = get_supabase()

    def execute(self, query):
        """Execute a query - simplified for Supabase."""
        # This is a simplified mock - real implementation would parse SQL
        # For now, we'll handle this in the agents directly
        logger.warning(f"Direct SQL execution not supported: {query}")
        return None

    def commit(self):
        """Mock commit."""
        pass

    def rollback(self):
        """Mock rollback."""
        pass

    def close(self):
        """Mock close."""
        pass


def get_db() -> Generator[SupabaseSession, None, None]:
    """
    Get database session for dependency injection.
    Returns a Supabase-backed session instead of SQLAlchemy.
    """
    session = SupabaseSession()
    try:
        yield session
    finally:
        session.close()


def check_db_connection() -> bool:
    """Check if Supabase connection is working."""
    try:
        client = get_supabase()
        result = client.table("tickets").select("ticket_id").limit(1).execute()
        logger.info("✅ Supabase connection successful")
        return True
    except Exception as e:
        logger.error(f"❌ Supabase connection failed: {e}")
        return False
