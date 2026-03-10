"""Router agent with reasoning engine for better query understanding."""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from app.agents.sql_agent_supabase import SQLAgent
from app.agents.rag_agent_supabase import RAGAgent
from app.agents.reasoning_engine import ReasoningEngine
from app.database.supabase_db import SupabaseDB

logger = logging.getLogger(__name__)


class RouterAgent:
    """Router agent with reasoning engine for intelligent query routing."""

    def __init__(self):
        self.reasoning_engine = ReasoningEngine()
        self.sql_agent = SQLAgent()
        self.rag_agent = RAGAgent()

    def route_and_answer(self, db: SupabaseDB, question: str) -> Dict[str, Any]:
        """Route question using reasoning engine, then get answer."""
        logger.info(f"🧠 Routing: {question}")

        analysis = self.reasoning_engine.analyze_question(question)
        plan = self.reasoning_engine.create_execution_plan(question, analysis)

        db_filters = analysis.get("db_filters", {})
        # organization_name may be in db_filters (new) or organization (old fallback)
        organization = db_filters.get("organization_name") or analysis.get("organization")
        query_type = analysis.get("query_type", "analytics")
        time_filter = self._parse_time_filter(analysis.get("time_filter"))

        logger.info(f"📋 Plan: {plan['reasoning']}")
        logger.info(f"🎯 Filters: {db_filters} | Type: {query_type} | Time: {analysis.get('time_filter')}")

        if query_type == "analytics":
            logger.info("📊 Using SQL Analytics Agent")
            result = self._execute_sql_query(db, question, organization, analysis, time_filter, db_filters)
        else:
            logger.info("🔍 Using Semantic Search Agent")
            result = self.rag_agent.answer_question(db, question, organization=organization)

        result["reasoning"] = plan["reasoning"]
        result["query_type"] = "analytics" if query_type == "analytics" else "lookup"
        return result

    def _execute_sql_query(
        self,
        db: SupabaseDB,
        question: str,
        organization: Optional[str],
        analysis: Dict[str, Any],
        time_filter: Optional[Dict[str, datetime]],
        db_filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute SQL query, passing db_filters + time_filter from reasoning engine."""
        intent = analysis.get("intent", "count")
        db_filters = db_filters or {}

        if intent == "count":
            return self._handle_count_with_filters(db, question, db_filters, time_filter)
        else:
            # top_n, list, etc.
            return self.sql_agent.answer_question(
                db, question,
                organization=organization,
                time_filter=time_filter,
                db_filters=db_filters,
            )

    def _handle_count_with_filters(
        self,
        db: SupabaseDB,
        question: str,
        db_filters: Dict[str, Any],
        time_filter: Optional[Dict[str, datetime]],
    ) -> Dict[str, Any]:
        """Handle count queries with db_filters dict from reasoning engine."""
        organization = db_filters.get("organization_name")
        tickets = []

        if not db_filters:
            count = db.execute_count_query("tickets", date_range=time_filter)
            tickets = db.execute_select_query(
                "tickets",
                columns="ticket_id,subject,organization_name,priority,status,created_at",
                order_by="-created_at",
                limit=5,
                date_range=time_filter,
            )
        else:
            count = db.execute_count_query("tickets", db_filters, date_range=time_filter)

            # If zero with exact org match, try case-insensitive fuzzy org match
            if count == 0 and organization:
                non_org_filters = {k: v for k, v in db_filters.items() if k != "organization_name"}
                all_tickets = db.execute_select_query(
                    "tickets",
                    columns="ticket_id,subject,organization_name,priority,status,created_at",
                    filters=non_org_filters if non_org_filters else None,
                    order_by="-created_at",
                    limit=5000,
                    date_range=time_filter,
                )
                org_lower = organization.lower()
                matching = [
                    t for t in all_tickets
                    if org_lower in (t.get("organization_name") or "").lower()
                ]
                count = len(matching)
                tickets = matching[:5]
            else:
                tickets = db.execute_select_query(
                    "tickets",
                    columns="ticket_id,subject,organization_name,priority,status,created_at",
                    filters=db_filters,
                    order_by="-created_at",
                    limit=5,
                    date_range=time_filter,
                )

        # Build human-readable answer
        answer = f"Found **{count}** ticket{'s' if count != 1 else ''}"
        filter_parts = []
        if organization:
            filter_parts.append(f"**{organization}**")
        for key, value in db_filters.items():
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
                "filters": db_filters,
                "query_type": "count",
                "time_filter": str(time_filter) if time_filter else None,
            },
        }

    def _parse_time_filter(self, time_str: Optional[str]) -> Optional[Dict[str, datetime]]:
        """Convert reasoning engine's time string to a date range dict."""
        if not time_str:
            return None
        t = time_str.lower()
        now = datetime.now()

        if "last week" in t or "past week" in t:
            return {"start_date": now - timedelta(days=7), "end_date": now}
        elif "last month" in t or "past month" in t:
            return {"start_date": now - timedelta(days=30), "end_date": now}
        elif "this week" in t:
            return {"start_date": now - timedelta(days=now.weekday()), "end_date": now}
        elif "this month" in t:
            return {"start_date": now.replace(day=1), "end_date": now}
        elif "today" in t:
            return {"start_date": now.replace(hour=0, minute=0, second=0), "end_date": now}
        elif "last year" in t or "past year" in t:
            return {"start_date": now - timedelta(days=365), "end_date": now}
        return None
