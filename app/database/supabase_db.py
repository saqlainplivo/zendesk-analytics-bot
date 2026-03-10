"""Supabase database layer using REST API (works over HTTPS, bypasses firewall)."""

import logging
from typing import Any, Dict, List, Optional, Generator
from datetime import datetime, timedelta
from supabase import create_client, Client

from app.config import settings

logger = logging.getLogger(__name__)

# Global Supabase client
_supabase_client: Optional[Client] = None


def get_supabase() -> Client:
    """Get or create Supabase client."""
    global _supabase_client

    if _supabase_client is None:
        _supabase_client = create_client(
            settings.supabase_url,
            settings.supabase_anon_key
        )
        logger.info("✅ Supabase client initialized")

    return _supabase_client


class SupabaseDB:
    """Database operations using Supabase REST API."""

    def __init__(self):
        self.client = get_supabase()

    def execute_count_query(
        self,
        table: str,
        filters: Optional[Dict[str, Any]] = None,
        date_range: Optional[Dict[str, Any]] = None
    ) -> int:
        """Execute a count query on a table."""
        try:
            query = self.client.table(table).select("*", count="exact")

            if filters:
                for key, value in filters.items():
                    if isinstance(value, list):
                        query = query.in_(key, value)
                    else:
                        query = query.eq(key, value)

            if date_range:
                if date_range.get("start_date"):
                    query = query.gte("created_at", date_range["start_date"].isoformat())
                if date_range.get("end_date"):
                    query = query.lte("created_at", date_range["end_date"].isoformat())

            result = query.execute()
            return result.count if result.count is not None else 0
        except Exception as e:
            logger.error(f"Count query error: {e}")
            # If a column doesn't exist yet (schema migration pending), retry without those filters
            if filters and ("column" in str(e).lower() or "PGRST" in str(e) or "does not exist" in str(e)):
                logger.warning("Column filter error — schema migration may be pending. Retrying without extra filters.")
                org_only = {k: v for k, v in filters.items() if k in ("organization_name", "status", "priority")}
                if org_only != filters:
                    return self.execute_count_query(table, org_only if org_only else None, date_range)
            return 0

    def execute_select_query(
        self,
        table: str,
        columns: str = "*",
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None,
        limit: Optional[int] = None,
        date_range: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Execute a select query on a table."""
        try:
            query = self.client.table(table).select(columns)

            if filters:
                for key, value in filters.items():
                    if isinstance(value, list):
                        query = query.in_(key, value)
                    else:
                        query = query.eq(key, value)

            if date_range:
                if date_range.get("start_date"):
                    query = query.gte("created_at", date_range["start_date"].isoformat())
                if date_range.get("end_date"):
                    query = query.lte("created_at", date_range["end_date"].isoformat())

            if order_by:
                desc = order_by.startswith("-")
                column = order_by.lstrip("-")
                query = query.order(column, desc=desc)

            if limit:
                query = query.limit(limit)

            result = query.execute()
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"Select query error: {e}")
            # If a column filter doesn't exist yet (schema migration pending), retry without extra filters
            if filters and ("column" in str(e).lower() or "PGRST" in str(e) or "does not exist" in str(e)):
                logger.warning("Column filter error — schema migration may be pending. Retrying without extra filters.")
                safe_keys = ("organization_name", "status", "priority")
                safe_filters = {k: v for k, v in filters.items() if k in safe_keys}
                if safe_filters != filters:
                    return self.execute_select_query(table, columns, safe_filters if safe_filters else None,
                                                     order_by, limit, date_range)
            return []

    def get_tickets_by_organization(
        self,
        organization: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get tickets filtered by organization and date range."""
        try:
            query = self.client.table("tickets").select("*")
            query = query.eq("organization_name", organization)

            if start_date:
                query = query.gte("created_at", start_date.isoformat())
            if end_date:
                query = query.lte("created_at", end_date.isoformat())

            query = query.order("created_at", desc=True)

            if limit:
                query = query.limit(limit)

            result = query.execute()
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"Get tickets by org error: {e}")
            return []

    def get_top_organizations(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top organizations by ticket count (paginated across all tickets)."""
        try:
            all_rows = []
            page, PAGE_SIZE = 0, 1000
            while True:
                result = (self.client.table("tickets")
                          .select("organization_name")
                          .range(page * PAGE_SIZE, (page + 1) * PAGE_SIZE - 1)
                          .execute())
                if not result.data:
                    break
                all_rows.extend(result.data)
                if len(result.data) < PAGE_SIZE:
                    break
                page += 1

            if not all_rows:
                return []

            org_counts: Dict[str, int] = {}
            for ticket in all_rows:
                org = ticket.get("organization_name") or "Unknown"
                org_counts[org] = org_counts.get(org, 0) + 1

            top_orgs = sorted(
                [{"organization": org, "ticket_count": count} for org, count in org_counts.items()],
                key=lambda x: x["ticket_count"],
                reverse=True
            )[:limit]

            return top_orgs
        except Exception as e:
            logger.error(f"Get top organizations error: {e}")
            return []

    def search_similar_tickets(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """Search for similar tickets using vector similarity."""
        try:
            result = self.client.rpc(
                "match_tickets",
                {
                    "query_embedding": query_embedding,
                    "match_threshold": threshold,
                    "match_count": top_k
                }
            ).execute()

            if not result.data:
                logger.info("No tickets above similarity threshold")
                return []

            # Enrich with full ticket data (select * to handle schema before/after migration)
            ticket_ids = [str(r["ticket_id"]) for r in result.data]
            similarities = {str(r["ticket_id"]): r.get("similarity", 0) for r in result.data}

            enriched = self.client.table("tickets").select("*").in_("ticket_id", ticket_ids).execute()

            if not enriched.data:
                return result.data  # fallback to raw RPC result

            for t in enriched.data:
                t["similarity"] = similarities.get(str(t["ticket_id"]), 0)

            enriched.data.sort(key=lambda x: x["similarity"], reverse=True)
            return enriched.data

        except Exception as e:
            logger.error(f"Vector search error: {e}")
            try:
                fallback = self.client.table("tickets").select("*").order("created_at", desc=True).limit(top_k).execute()
                return fallback.data if fallback.data else []
            except:
                return []

    def get_ticket_by_id(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        """Get a single ticket by ID."""
        try:
            result = self.client.table("tickets").select("*").eq("ticket_id", ticket_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Get ticket by ID error: {e}")
            return None

    def close(self):
        """Close connection (no-op for Supabase client)."""
        pass


def get_db() -> Generator[SupabaseDB, None, None]:
    """
    Get database session for dependency injection.
    Returns Supabase-backed database connection.
    """
    db = SupabaseDB()
    try:
        yield db
    finally:
        db.close()


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
