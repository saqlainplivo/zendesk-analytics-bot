"""Reasoning engine that thinks before executing queries."""

import logging
import json
from typing import Dict, Any, Optional
import openai

from app.config import settings

logger = logging.getLogger(__name__)


class ReasoningEngine:
    """
    Reasoning engine that analyzes questions and plans query execution.
    Uses LLM to extract intent, parameters, and generate execution plan.
    """

    def __init__(self):
        """Initialize reasoning engine."""
        self.client = openai.OpenAI(api_key=settings.openai_api_key)

    def analyze_question(self, question: str) -> Dict[str, Any]:
        """
        Analyze question and extract structured information.

        Args:
            question: Natural language question

        Returns:
            Dictionary with reasoning and parameters
        """
        logger.info(f"Reasoning Engine analyzing: {question}")

        system_prompt = """You are a query analyzer for a Zendesk ticket analytics system.

The tickets database has these columns you can filter on:
- organization_name : customer/company name (e.g. "Kixie", "Plivo Inc", "Google")
- priority          : "Normal", "High", "Low", "Urgent"
- status            : "open", "closed", "pending", "solved", "new"
- ticket_type       : "Incident", "Problem", "Question", "Task"
- support_tier      : "Tier 1", "Tier 2", "Tier 3", "Tier 4", "Tier 5"
- product           : "Messaging API", "Voice API", "SIP Trunking", "PlivoCX"
- country           : country name e.g. "US", "INDIA", "PHILIPPINES"
- assignee          : agent/assignee name
- group_name        : support team name

Your job is to extract:
1. **intent**     : count | list | top_n | search | summary
2. **query_type** : "analytics" (counts, rankings, lists) or "lookup" (semantic search, summaries, "what issues")
3. **time_filter**: natural language time period or null
4. **db_filters** : dict of column→value for EVERY filter condition in the question.
                    Use exact column names from the list above.
                    Only include filters explicitly mentioned.

Return ONLY a JSON object:
{
    "reasoning"  : "step-by-step explanation",
    "intent"     : "count|list|top_n|search|summary",
    "query_type" : "analytics|lookup",
    "time_filter": "last month|last week|this year|... or null",
    "db_filters" : {
        "organization_name": "...",
        "priority": "...",
        "support_tier": "...",
        ... only what is mentioned
    }
}

Examples:

Q: "How many Tier 1 Kixie tickets in the past year?"
A: {
    "reasoning": "Count tickets filtered by org=Kixie, tier=Tier 1, time=past year",
    "intent": "count",
    "query_type": "analytics",
    "time_filter": "last year",
    "db_filters": {"organization_name": "Kixie", "support_tier": "Tier 1"}
}

Q: "how many high priority open incidents from Bolna last month?"
A: {
    "reasoning": "Count open high-priority incidents from Bolna last month",
    "intent": "count",
    "query_type": "analytics",
    "time_filter": "last month",
    "db_filters": {"organization_name": "Bolna", "priority": "High", "status": "open", "ticket_type": "Incident"}
}

Q: "top 5 customers by ticket count"
A: {
    "reasoning": "Rank top 5 orgs by ticket volume",
    "intent": "top_n",
    "query_type": "analytics",
    "time_filter": null,
    "db_filters": {}
}

Q: "how many tickets were raised by Kixie?"
A: {
    "reasoning": "Count all tickets from Kixie",
    "intent": "count",
    "query_type": "analytics",
    "time_filter": null,
    "db_filters": {"organization_name": "Kixie"}
}

Q: "what issues did Kixie face last month?"
A: {
    "reasoning": "Semantic search for Kixie issues - needs RAG not SQL",
    "intent": "search",
    "query_type": "lookup",
    "time_filter": "last month",
    "db_filters": {"organization_name": "Kixie"}
}

Q: "show me all Messaging API tickets"
A: {
    "reasoning": "List tickets filtered by product=Messaging API",
    "intent": "list",
    "query_type": "analytics",
    "time_filter": null,
    "db_filters": {"product": "Messaging API"}
}"""

        try:
            response = self.client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Analyze this question: {question}\n\nReturn ONLY a JSON object, no other text."}
                ],
                temperature=0.0  # Deterministic
            )

            content = response.choices[0].message.content.strip()

            # Try to extract JSON if wrapped in markdown
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            analysis = json.loads(content)
            logger.info(f"Analysis complete: {analysis}")

            return analysis

        except Exception as e:
            logger.error(f"Reasoning error: {e}")
            # Fallback to basic extraction
            return {
                "reasoning": "Fallback analysis - basic pattern matching",
                "intent": "count",
                "organization": None,
                "time_filter": None,
                "query_type": "analytics",
                "filters": {}
            }

    def create_execution_plan(
        self,
        question: str,
        analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create execution plan based on analysis.

        Args:
            question: Original question
            analysis: Analysis from analyze_question

        Returns:
            Execution plan dictionary
        """
        db_filters = analysis.get("db_filters", {})
        plan = {
            "reasoning": analysis.get("reasoning", ""),
            "query_type": analysis.get("query_type", "analytics"),
            "filters": {
                "db_filters": db_filters,
                "time_filter": analysis.get("time_filter")
            },
            "intent": analysis.get("intent", "count"),
            "original_question": question
        }

        logger.info(f"Execution plan: {plan}")
        return plan
