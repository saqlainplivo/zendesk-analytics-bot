"""Router agent with reasoning engine for better query understanding."""

import logging
from typing import Dict, Any

from app.agents.sql_agent_supabase import SQLAgent
from app.agents.rag_agent_supabase import RAGAgent
from app.agents.groq_reasoning_engine import GroqReasoningEngine
from app.agents.nvidia_reasoning_engine import NvidiaReasoningEngine
from app.database.supabase_db import SupabaseDB
from app.config import settings
from app.utils.time_parser import TimeParser

logger = logging.getLogger(__name__)


class RouterAgent:
    """Router agent with reasoning engine for intelligent query routing."""

    def __init__(self):
        """Initialize router with configurable reasoning engine and specialized agents."""
        # Select reasoning engine based on config
        engine_type = settings.reasoning_engine.lower()
        if engine_type == "nvidia":
            self.reasoning_engine = NvidiaReasoningEngine()
            logger.info("🎯 Using NVIDIA NIM reasoning engine")
        elif engine_type == "groq":
            self.reasoning_engine = GroqReasoningEngine()
            logger.info("🚀 Using Groq reasoning engine")
        else:
            self.reasoning_engine = GroqReasoningEngine()  # Default
            logger.info("🚀 Using Groq reasoning engine (default)")

        self.sql_agent = SQLAgent()
        self.rag_agent = RAGAgent()

    def route_and_answer(
        self,
        db: SupabaseDB,
        question: str
    ) -> Dict[str, Any]:
        """
        Route question using reasoning engine, then get answer.

        Args:
            db: Supabase database instance
            question: Natural language question

        Returns:
            Answer dictionary with reasoning, response, and evidence
        """
        logger.info(f"🧠 Routing question with reasoning: {question}")

        # Step 1: Analyze question with reasoning engine
        analysis = self.reasoning_engine.analyze_question(question)

        # Step 2: Create execution plan
        plan = self.reasoning_engine.create_execution_plan(question, analysis)

        # Extract parameters from analysis
        organization = analysis.get("organization")
        query_type = analysis.get("query_type", "analytics")

        logger.info(f"📋 Plan: {plan['reasoning']}")
        logger.info(f"🎯 Organization: {organization}")
        logger.info(f"🔀 Query type: {query_type}")

        # Step 3: Execute query with appropriate agent
        # Override the question with enhanced version if we have filters
        enhanced_question = question
        if organization and organization.lower() not in question.lower():
            enhanced_question = f"{question} (filtering by organization: {organization})"

        if query_type == "analytics":
            # Use SQL agent with extracted parameters
            logger.info("📊 Using SQL Analytics Agent")
            result = self._execute_sql_query(db, question, organization, analysis)
        else:
            # Use RAG agent
            logger.info("🔍 Using Semantic Search Agent")
            result = self.rag_agent.answer_question(db, enhanced_question)

        # Step 4: Add reasoning to result
        result["reasoning"] = plan["reasoning"]
        result["query_type"] = "analytics" if query_type == "analytics" else "lookup"

        return result

    def _execute_sql_query(
        self,
        db: SupabaseDB,
        question: str,
        organization: str,
        analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute SQL query with enhanced organization filtering."""
        intent = analysis.get("intent", "count")

        # Direct database query based on intent
        if intent == "count":
            return self._handle_count_with_org(db, question, organization)
        elif intent == "list":
            return self._handle_list_with_org(db, question, organization, analysis)
        elif intent == "top_n":
            return self.sql_agent.answer_question(db, question)
        else:
            return self.sql_agent.answer_question(db, question)

    def _handle_count_with_org(
        self,
        db: SupabaseDB,
        question: str,
        organization: str
    ) -> Dict[str, Any]:
        """Handle count queries with fuzzy organization filtering."""
        # Parse time filter if present
        time_range = TimeParser.parse_time_filter(question)

        # Extract status filter for SQL query optimization
        question_lower = question.lower()
        status_filter = None
        if "open" in question_lower and not organization:
            status_filter = "open"
        elif "closed" in question_lower and not organization:
            status_filter = "closed"
        elif "pending" in question_lower and not organization:
            status_filter = "pending"

        if not organization:
            # No organization filter - use SQL filters directly
            filters = {}
            if status_filter:
                filters["status"] = status_filter

            count = db.execute_count_query("tickets", filters if filters else None)
            tickets = db.execute_select_query(
                "tickets",
                columns="ticket_id,subject,organization_name,priority,status,created_at,description",
                filters=filters if filters else None,
                order_by="-created_at",
                limit=5
            )
        else:
            # Fuzzy matching with Python (Supabase ilike has issues with wildcards)
            org_lower = organization.lower().strip()
            logger.info(f"🔍 Fuzzy matching organization: '{org_lower}'")

            # Fetch all tickets (Supabase has 1000 record limit, so we'll paginate)
            all_tickets = []
            offset = 0
            batch_size = 1000

            while True:
                batch = db.client.table("tickets").select(
                    "ticket_id,subject,organization_name,priority,status,created_at,description"
                ).order("created_at", desc=True).range(offset, offset + batch_size - 1).execute()

                if not batch.data:
                    break

                all_tickets.extend(batch.data)
                offset += batch_size

                # Stop if we got less than batch_size (last page)
                if len(batch.data) < batch_size:
                    break

            logger.info(f"📥 Fetched {len(all_tickets)} tickets for fuzzy matching")

            # Python-side fuzzy matching with time filter
            matching_tickets = []
            for t in all_tickets:
                org_name = t.get('organization_name', '').lower().strip()

                # Match organization
                if org_lower not in org_name:
                    continue

                # Apply time filter if specified
                if time_range:
                    created_at_str = t.get('created_at')
                    if created_at_str:
                        try:
                            from dateutil import parser as date_parser
                            created_at = date_parser.parse(created_at_str)
                            if not (time_range[0] <= created_at <= time_range[1]):
                                continue
                        except:
                            pass

                matching_tickets.append(t)

        count = len(matching_tickets)
        tickets = matching_tickets[:5]

        # Only apply additional filters if explicitly mentioned in question
        question_lower = question.lower()
        has_priority_filter = any(kw in question_lower for kw in ["high", "urgent", "critical", "low", "normal", "priority"])
        has_status_filter = any(kw in question_lower for kw in ["open", "closed", "pending", "solved", "resolved"])

        if matching_tickets and (has_priority_filter or has_status_filter):
            filtered = self._apply_additional_filters(matching_tickets, question)
            if filtered:  # Only apply if we still have results
                count = len(filtered)
                tickets = filtered[:5]
                logger.info(f"🎯 Applied filters: priority={has_priority_filter}, status={has_status_filter}")

        if count > 0:
                unique_orgs = set(t.get('organization_name') for t in matching_tickets[:10])
                if time_range:
                    time_desc = TimeParser.format_time_range(time_range[0], time_range[1])
                    logger.info(f"✓ Found {count} tickets matching '{organization}' {time_desc}")
                else:
                    logger.info(f"✓ Found {count} tickets matching '{organization}' in orgs: {list(unique_orgs)}")

        evidence = [t["ticket_id"] for t in tickets]

        # Generate answer
        answer = f"Found {count} ticket{'s' if count != 1 else ''}"
        if organization:
            answer += f" for **{organization}**"
        answer += "."

        if count > 0 and tickets:
            answer += f"\n\n**Most recent:**\n"
            for i, t in enumerate(tickets[:3], 1):
                answer += f"{i}. {t.get('subject', 'N/A')} (#{t['ticket_id']})\n"

        return {
            "answer": answer,
            "evidence": evidence,
            "evidence_details": tickets,
            "metadata": {
                "count": count,
                "organization": organization,
                "query_type": "count"
            }
        }

    def _handle_list_with_org(
        self,
        db: SupabaseDB,
        question: str,
        organization: str,
        analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle list queries with organization filtering."""
        # Extract filters from question
        question_lower = question.lower()
        status_filter = None
        priority_filter = None

        # Detect status filter
        if "open" in question_lower or "active" in question_lower:
            status_filter = "open"
        elif "closed" in question_lower:
            status_filter = "closed"
        elif "pending" in question_lower or "waiting" in question_lower:
            status_filter = "pending"
        elif "solved" in question_lower or "resolved" in question_lower:
            status_filter = "solved"

        # Detect priority filter
        if "high" in question_lower or "urgent" in question_lower:
            priority_filter = "high"
        elif "low" in question_lower:
            priority_filter = "low"
        elif "normal" in question_lower:
            priority_filter = "normal"

        if not organization:
            # No organization filter - fetch tickets with SQL filters if possible
            filters = {}
            if status_filter:
                filters["status"] = status_filter
                logger.info(f"🎯 Applying direct status filter: {status_filter}")

            tickets = db.execute_select_query(
                "tickets",
                columns="ticket_id,subject,organization_name,priority,status,created_at,description",
                filters=filters if filters else None,
                order_by="-created_at",
                limit=10
            )
            count = db.execute_count_query("tickets", filters if filters else None)
        else:
            # Fuzzy matching for organization
            org_lower = organization.lower().strip()
            logger.info(f"🔍 Listing tickets for: '{org_lower}'")

            # Fetch all tickets and fuzzy match
            all_tickets = []
            offset = 0
            batch_size = 1000

            while True:
                batch = db.client.table("tickets").select(
                    "ticket_id,subject,organization_name,priority,status,created_at,description"
                ).order("created_at", desc=True).range(offset, offset + batch_size - 1).execute()

                if not batch.data:
                    break

                all_tickets.extend(batch.data)
                offset += batch_size

                if len(batch.data) < batch_size:
                    break

            # Python-side fuzzy matching
            matching_tickets = [
                t for t in all_tickets
                if org_lower in t.get('organization_name', '').lower().strip()
            ]

            count = len(matching_tickets)
            tickets = matching_tickets[:10]

            if count > 0:
                unique_orgs = set(t.get('organization_name') for t in matching_tickets[:10])
                logger.info(f"✓ Found {count} tickets from: {list(unique_orgs)}")

        # Only apply additional filters if explicitly mentioned
        question_lower = question.lower()
        has_priority_filter = any(kw in question_lower for kw in ["high", "urgent", "critical", "low", "normal", "priority"])
        has_status_filter = any(kw in question_lower for kw in ["open", "closed", "pending", "solved", "resolved"])

        if tickets and (has_priority_filter or has_status_filter):
            filtered = self._apply_additional_filters(tickets, question)
            if filtered:  # Only apply if we still have results
                count = len(filtered)
                tickets = filtered[:10]

        evidence = [t["ticket_id"] for t in tickets]

        # Generate answer with ticket list
        if count == 0:
            answer = f"No tickets found"
            if organization:
                answer += f" for **{organization}**"
            answer += "."
        else:
            answer = f"Found **{count}** ticket{'s' if count != 1 else ''}"
            if organization:
                answer += f" from **{organization}**"
            answer += ":\n\n"

            for i, t in enumerate(tickets[:10], 1):
                priority = t.get('priority', 'N/A')
                status = t.get('status', 'N/A')
                subject = t.get('subject', 'N/A')
                ticket_id = t['ticket_id']

                answer += f"{i}. [{priority.upper()}] {subject}\n"
                answer += f"   Status: {status} | ID: #{ticket_id}\n\n"

            if count > 10:
                answer += f"\n*Showing 10 of {count} total tickets*"

        return {
            "answer": answer,
            "evidence": evidence,
            "evidence_details": tickets,
            "metadata": {
                "count": count,
                "organization": organization,
                "query_type": "list"
            }
        }

    def _apply_additional_filters(
        self,
        tickets: list,
        question: str
    ) -> list:
        """Apply priority and status filters from question (lenient matching)."""
        question_lower = question.lower()
        filtered = tickets

        # Priority filter (more lenient, includes N/A as potential match)
        priority_keywords = {
            "high": ["high priority", "high"],
            "urgent": ["urgent", "critical"],
            "low": ["low priority", "low"],
            "normal": ["normal", "medium"]
        }

        for priority, keywords in priority_keywords.items():
            if any(kw in question_lower for kw in keywords):
                # Include tickets with matching priority OR missing priority (to be lenient)
                filtered = [
                    t for t in filtered
                    if t.get('priority', '').lower() in [priority, 'urgent', 'critical', 'high', ''] or
                       (priority == 'high' and t.get('priority', '').lower() in ['urgent', 'critical']) or
                       t.get('priority', '') in ['N/A', None, '']  # Include missing priorities
                ]
                logger.info(f"🎯 Applied lenient priority filter: {priority} (kept {len(filtered)} tickets)")
                break

        # Status filter (more lenient)
        status_keywords = {
            "open": ["open", "active"],
            "closed": ["closed"],
            "pending": ["pending", "waiting"],
            "solved": ["solved", "resolved"]
        }

        for status, keywords in status_keywords.items():
            if any(kw in question_lower for kw in keywords):
                # More lenient matching
                status_variations = {
                    "open": ["open", "new", "active"],
                    "closed": ["closed", "solved"],
                    "pending": ["pending", "hold", "waiting"],
                    "solved": ["solved", "resolved", "closed"]
                }

                allowed_statuses = status_variations.get(status, [status])
                filtered = [
                    t for t in filtered
                    if t.get('status', '').lower() in allowed_statuses or
                       t.get('status', '') in ['N/A', None, '']  # Include missing status
                ]
                logger.info(f"🎯 Applied lenient status filter: {status} (kept {len(filtered)} tickets)")
                break

        return filtered
