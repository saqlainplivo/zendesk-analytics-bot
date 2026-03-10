"""SQL agent using Supabase REST API with improved filtering."""

import logging
import re
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import openai

from app.database.supabase_db import SupabaseDB
from app.config import settings

logger = logging.getLogger(__name__)


class SQLAgent:
    """SQL analytics agent using Supabase REST API."""

    def __init__(self):
        self.client = openai.OpenAI(api_key=settings.openai_api_key)

    def answer_question(
        self,
        db: SupabaseDB,
        question: str,
        organization: Optional[str] = None,
        time_filter: Optional[Dict[str, datetime]] = None,
        db_filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Answer analytics questions using Supabase queries.

        Args:
            organization: Pre-extracted org name (from reasoning engine).
                          If None, falls back to regex extraction from question.
            time_filter:  Pre-parsed date range dict with start_date/end_date.
                          If None, falls back to extraction from question.
            db_filters:   Full filter dict from reasoning engine (includes priority,
                          support_tier, status, etc.). Takes precedence over organization.
        """
        logger.info(f"SQL Agent processing: {question}")

        # If db_filters provided, use organization_name from it; else fall back to regex
        if db_filters:
            organization = db_filters.get("organization_name") or organization
        elif organization is None:
            organization = self._extract_organization(question)

        if time_filter is None:
            time_filter = self._extract_time_filter(question)

        logger.info(f"Organization: {organization}")
        logger.info(f"DB Filters: {db_filters}")
        logger.info(f"Time filter: {time_filter}")

        question_lower = question.lower()

        # Check "top" before "count" — "top 5 by ticket count" contains "count"
        if "top" in question_lower or "most" in question_lower:
            return self._handle_top_query(db, question, organization, time_filter)
        elif "how many" in question_lower or "count" in question_lower:
            return self._handle_count_query(db, question, organization, time_filter, db_filters)
        elif "list" in question_lower or "show" in question_lower:
            return self._handle_list_query(db, question, organization, time_filter, db_filters)
        else:
            return self._handle_count_query(db, question, organization, time_filter, db_filters)

    def _handle_count_query(
        self,
        db: SupabaseDB,
        question: str,
        organization: Optional[str],
        time_filter: Optional[Dict[str, datetime]],
        db_filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Handle count queries."""
        filters = dict(db_filters) if db_filters else {}
        if organization and "organization_name" not in filters:
            filters["organization_name"] = organization

        count = db.execute_count_query("tickets", filters, date_range=time_filter)
        tickets = []

        # If zero with exact org match, try case-insensitive fuzzy
        if count == 0 and organization:
            non_org = {k: v for k, v in filters.items() if k != "organization_name"}
            all_tickets = db.execute_select_query(
                "tickets",
                columns="ticket_id,subject,organization_name,priority,status,created_at",
                filters=non_org if non_org else None,
                order_by="-created_at",
                limit=5000,
                date_range=time_filter,
            )
            org_lower = organization.lower()
            matching = [t for t in all_tickets if org_lower in (t.get("organization_name") or "").lower()]
            count = len(matching)
            tickets = matching[:5]
        else:
            tickets = db.execute_select_query(
                "tickets",
                columns="ticket_id,subject,organization_name,priority,status,created_at",
                filters=filters if filters else None,
                order_by="-created_at",
                limit=5,
                date_range=time_filter,
            )

        answer = f"Found **{count}** ticket{'s' if count != 1 else ''}"
        filter_parts = []
        if organization:
            filter_parts.append(f"**{organization}**")
        for key, value in filters.items():
            if key == "organization_name":
                continue
            label = key.replace("_", " ").title()
            filter_parts.append(f"{label}: **{value}**")
        if filter_parts:
            answer += " matching " + ", ".join(filter_parts)
        if time_filter:
            answer += " in the specified time period"
        answer += "."

        if count > 0 and tickets:
            answer += "\n\n**Most recent:**\n"
            for i, t in enumerate(tickets[:3], 1):
                answer += f"{i}. {t.get('subject', 'N/A')} (#{t['ticket_id']})\n"

        return {
            "answer": answer,
            "evidence": [t["ticket_id"] for t in tickets],
            "evidence_details": tickets,
            "metadata": {
                "count": count,
                "query_type": "count",
                "filters": filters,
                "time_filter": str(time_filter) if time_filter else None,
            },
        }

    def _handle_top_query(
        self,
        db: SupabaseDB,
        question: str,
        organization: Optional[str],
        time_filter: Optional[Dict[str, datetime]],
    ) -> Dict[str, Any]:
        """Handle top-N queries."""
        limit = 10
        match = re.search(r"top\s+(\d+)", question.lower())
        if match:
            limit = int(match.group(1))

        if any(w in question.lower() for w in ("organization", "customer", "contributor", "company")):
            top_orgs = db.get_top_organizations(limit=limit)

            if not top_orgs:
                return {
                    "answer": "No data available.",
                    "evidence": [],
                    "evidence_details": [],
                    "metadata": {"query_type": "top_organizations"},
                }

            lines = [f"**Top {len(top_orgs)} organizations by ticket count:**\n"]
            for i, org in enumerate(top_orgs, 1):
                lines.append(f"{i}. **{org['organization']}** — {org['ticket_count']} tickets")
            answer = "\n".join(lines)

            sample_tickets = db.get_tickets_by_organization(top_orgs[0]["organization"], limit=5)
            return {
                "answer": answer,
                "evidence": [t["ticket_id"] for t in sample_tickets],
                "evidence_details": sample_tickets,
                "metadata": {"query_type": "top_organizations", "results": top_orgs},
            }

        return self._handle_list_query(db, question, organization, time_filter)

    def _handle_list_query(
        self,
        db: SupabaseDB,
        question: str,
        organization: Optional[str],
        time_filter: Optional[Dict[str, datetime]],
        db_filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Handle list/show queries."""
        filters = dict(db_filters) if db_filters else {}
        if organization and "organization_name" not in filters:
            filters["organization_name"] = organization

        tickets = db.execute_select_query(
            "tickets",
            columns="ticket_id,subject,organization_name,priority,status,created_at",
            filters=filters if filters else None,
            order_by="-created_at",
            limit=10,
            date_range=time_filter,
        )

        if not tickets:
            return {
                "answer": "No tickets found matching the criteria.",
                "evidence": [],
                "evidence_details": [],
                "metadata": {"query_type": "list"},
            }

        lines = [f"**{len(tickets)} recent tickets:**\n"]
        for i, t in enumerate(tickets, 1):
            lines.append(
                f"{i}. **{t['subject']}** (#{t['ticket_id']})\n"
                f"   Priority: {t.get('priority', 'N/A')} | Status: {t.get('status', 'N/A')}"
            )

        return {
            "answer": "\n".join(lines),
            "evidence": [t["ticket_id"] for t in tickets],
            "evidence_details": tickets,
            "metadata": {"query_type": "list", "ticket_count": len(tickets)},
        }

    def _extract_organization(self, question: str) -> Optional[str]:
        """Extract organization name — only for explicit org references, not analytics terms."""
        ANALYTICS_TERMS = {
            "ticket", "tickets", "count", "volume", "number", "most", "least",
            "organization", "organizations", "customer", "customers", "company",
            "companies", "contributor", "contributors", "priority", "status",
            "date", "time", "month", "week", "year",
        }

        patterns = [
            r"(?:from|for|about)\s+([A-Z][a-zA-Z0-9\s\-\.]{1,40}?)(?:\s+(?:raise|create|had|last|this|in|with|did|face|report)|\?|$)",
            r"(?:by)\s+([A-Z][a-zA-Z0-9\s\-\.]{1,40}?)(?:\s+(?:last|this|in|had|raise|create|did)|\?|$)",
            r"organization[:\s]+([a-zA-Z][a-zA-Z0-9\s\-\.]+?)(?:\s+|\?|$)",
        ]

        for pattern in patterns:
            match = re.search(pattern, question, re.IGNORECASE)
            if match:
                org = match.group(1).strip()
                org = re.sub(r"\s+(last|this|in|with|had|raise|create|did|were|was)$", "", org, flags=re.IGNORECASE).strip()
                if not org or len(org) <= 1:
                    continue
                if all(w.lower() in ANALYTICS_TERMS for w in org.split()):
                    continue
                logger.info(f"Extracted organization: {org}")
                return org

        return None

    def _extract_time_filter(self, question: str) -> Optional[Dict[str, datetime]]:
        """Extract time filter from question."""
        q = question.lower()
        now = datetime.now()

        if "last week" in q or "past week" in q:
            return {"start_date": now - timedelta(days=7), "end_date": now}
        elif "last month" in q or "past month" in q:
            return {"start_date": now - timedelta(days=30), "end_date": now}
        elif "this week" in q:
            return {"start_date": now - timedelta(days=now.weekday()), "end_date": now}
        elif "this month" in q:
            return {"start_date": now.replace(day=1), "end_date": now}
        elif "today" in q:
            return {"start_date": now.replace(hour=0, minute=0, second=0), "end_date": now}
        elif "last year" in q or "past year" in q:
            return {"start_date": now - timedelta(days=365), "end_date": now}

        return None
