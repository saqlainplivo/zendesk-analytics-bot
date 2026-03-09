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
        """Initialize SQL agent."""
        self.client = openai.OpenAI(api_key=settings.openai_api_key)

    def answer_question(
        self,
        db: SupabaseDB,
        question: str
    ) -> Dict[str, Any]:
        """Answer analytics questions using Supabase queries."""
        logger.info(f"SQL Agent processing: {question}")

        # Extract filters from question
        organization = self._extract_organization(question)
        time_filter = self._extract_time_filter(question)

        logger.info(f"Extracted organization: {organization}")
        logger.info(f"Extracted time filter: {time_filter}")

        # Determine query type and execute
        question_lower = question.lower()

        if "how many" in question_lower or "count" in question_lower:
            return self._handle_count_query(db, question, organization, time_filter)
        elif "top" in question_lower or "most" in question_lower:
            return self._handle_top_query(db, question, organization, time_filter)
        elif "list" in question_lower or "show" in question_lower:
            return self._handle_list_query(db, question, organization, time_filter)
        else:
            # Generic count query
            return self._handle_count_query(db, question, organization, time_filter)

    def _handle_count_query(
        self,
        db: SupabaseDB,
        question: str,
        organization: Optional[str],
        time_filter: Optional[Dict[str, datetime]]
    ) -> Dict[str, Any]:
        """Handle count queries."""
        filters = {}

        if organization:
            # Try exact match first, then case-insensitive
            filters["organization_name"] = organization

        count = db.execute_count_query("tickets", filters)

        # If no results with exact match, try case-insensitive search
        if count == 0 and organization:
            # Get all tickets and filter manually (for small datasets)
            all_tickets = db.execute_select_query(
                "tickets",
                columns="ticket_id,subject,organization_name,created_at",
                order_by="-created_at",
                limit=1000
            )

            # Case-insensitive search
            org_lower = organization.lower()
            matching_tickets = [
                t for t in all_tickets
                if org_lower in t.get('organization_name', '').lower()
            ]

            count = len(matching_tickets)
            tickets = matching_tickets[:5]
        else:
            # Get sample tickets as evidence
            tickets = db.execute_select_query(
                "tickets",
                columns="ticket_id,subject,organization_name,priority,status,created_at,description",
                filters=filters,
                order_by="-created_at",
                limit=5
            )

        evidence = [t["ticket_id"] for t in tickets]
        evidence_details = tickets  # Full ticket details for preview

        # Generate natural answer
        answer = f"Found {count} ticket{'s' if count != 1 else ''}"
        if organization:
            answer += f" from {organization}"
        answer += "."

        if count > 0 and tickets:
            answer += f"\n\nMost recent:\n"
            for i, t in enumerate(tickets[:3], 1):
                answer += f"{i}. {t.get('subject', 'N/A')} (#{t['ticket_id']})\n"

        return {
            "answer": answer,
            "evidence": evidence,
            "evidence_details": evidence_details,
            "metadata": {
                "count": count,
                "query_type": "count",
                "filters": filters,
                "organization": organization
            }
        }

    def _handle_top_query(
        self,
        db: SupabaseDB,
        question: str,
        organization: Optional[str],
        time_filter: Optional[Dict[str, datetime]]
    ) -> Dict[str, Any]:
        """Handle top N queries."""
        limit = 10
        match = re.search(r'top\s+(\d+)', question.lower())
        if match:
            limit = int(match.group(1))

        if "organization" in question.lower() or "customer" in question.lower() or "contributor" in question.lower():
            top_orgs = db.get_top_organizations(limit=limit)

            if not top_orgs:
                return {
                    "answer": "No data available.",
                    "evidence": [],
                    "evidence_details": [],
                    "metadata": {"query_type": "top_organizations"}
                }

            # Generate answer
            answer_lines = [f"Top {len(top_orgs)} organizations by ticket count:\n"]
            for i, org in enumerate(top_orgs, 1):
                answer_lines.append(
                    f"{i}. **{org['organization']}** - {org['ticket_count']} tickets"
                )

            answer = "\n".join(answer_lines)

            # Get sample tickets from top org
            sample_tickets = []
            evidence = []
            if top_orgs:
                sample_tickets = db.get_tickets_by_organization(
                    top_orgs[0]["organization"],
                    limit=5
                )
                evidence = [t["ticket_id"] for t in sample_tickets]

            return {
                "answer": answer,
                "evidence": evidence,
                "evidence_details": sample_tickets,
                "metadata": {
                    "query_type": "top_organizations",
                    "results": top_orgs
                }
            }

        # Default: list recent tickets
        return self._handle_list_query(db, question, organization, time_filter)

    def _handle_list_query(
        self,
        db: SupabaseDB,
        question: str,
        organization: Optional[str],
        time_filter: Optional[Dict[str, datetime]]
    ) -> Dict[str, Any]:
        """Handle list/show queries."""
        filters = {}
        if organization:
            filters["organization_name"] = organization

        tickets = db.execute_select_query(
            "tickets",
            columns="ticket_id,subject,organization_name,priority,status,created_at,description",
            filters=filters,
            order_by="-created_at",
            limit=10
        )

        if not tickets:
            return {
                "answer": "No tickets found matching the criteria.",
                "evidence": [],
                "evidence_details": [],
                "metadata": {"query_type": "list"}
            }

        # Generate answer
        answer_lines = [f"Found {len(tickets)} recent tickets:\n"]
        for i, ticket in enumerate(tickets, 1):
            answer_lines.append(
                f"{i}. **{ticket['subject']}** (#{ticket['ticket_id']})\n"
                f"   Priority: {ticket.get('priority', 'N/A')} | "
                f"Status: {ticket.get('status', 'N/A')}"
            )

        answer = "\n".join(answer_lines)
        evidence = [t["ticket_id"] for t in tickets]

        return {
            "answer": answer,
            "evidence": evidence,
            "evidence_details": tickets,
            "metadata": {
                "query_type": "list",
                "ticket_count": len(tickets)
            }
        }

    def _extract_organization(self, question: str) -> Optional[str]:
        """Extract organization name from question (case-insensitive)."""
        # Improved patterns - case insensitive, more flexible
        patterns = [
            r'(?:from|by|for|about)\s+([a-zA-Z][a-zA-Z0-9\s\-\.]+?)(?:\s+(?:raise|create|had|last|this|in|with|did|face|report)|\?|$)',
            r'organization[:\s]+([a-zA-Z][a-zA-Z0-9\s\-\.]+?)(?:\s+|\?|$)',
            r'customer[:\s]+([a-zA-Z][a-zA-Z0-9\s\-\.]+?)(?:\s+|\?|$)',
        ]

        for pattern in patterns:
            match = re.search(pattern, question, re.IGNORECASE)
            if match:
                org = match.group(1).strip()
                # Clean up common trailing words
                org = re.sub(r'\s+(last|this|in|with|had|raise|create|did|were|was)$', '', org, flags=re.IGNORECASE)
                org = org.strip()
                if len(org) > 1:  # At least 2 characters
                    logger.info(f"Extracted organization: '{org}'")
                    return org

        return None

    def _extract_time_filter(self, question: str) -> Optional[Dict[str, datetime]]:
        """Extract time filter from question."""
        question_lower = question.lower()
        now = datetime.now()

        if "last week" in question_lower or "past week" in question_lower:
            return {
                "start_date": now - timedelta(days=7),
                "end_date": now
            }
        elif "last month" in question_lower or "past month" in question_lower:
            return {
                "start_date": now - timedelta(days=30),
                "end_date": now
            }
        elif "this week" in question_lower:
            return {
                "start_date": now - timedelta(days=now.weekday()),
                "end_date": now
            }
        elif "this month" in question_lower:
            return {
                "start_date": now.replace(day=1),
                "end_date": now
            }
        elif "today" in question_lower:
            return {
                "start_date": now.replace(hour=0, minute=0, second=0),
                "end_date": now
            }

        return None
