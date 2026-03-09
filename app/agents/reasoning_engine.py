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

Your job is to analyze user questions and extract:
1. **Intent**: What the user wants (count, list, top_n, search, summary)
2. **Organization**: Company/organization name mentioned (case-sensitive extraction)
3. **Time Filter**: Any time period mentioned
4. **Query Type**: "analytics" (for counts, aggregations) or "lookup" (for semantic search)

Return a JSON object with:
{
    "reasoning": "Step-by-step analysis of what the user wants",
    "intent": "count|list|top_n|search|summary",
    "organization": "exact organization name or null",
    "time_filter": "time period or null",
    "query_type": "analytics|lookup",
    "filters": {
        "organization": "organization name",
        "time_period": "time period"
    }
}

Examples:

Q: "Bolna ticket count"
A: {
    "reasoning": "User wants to count tickets for organization 'Bolna'",
    "intent": "count",
    "organization": "Bolna",
    "time_filter": null,
    "query_type": "analytics",
    "filters": {"organization": "Bolna"}
}

Q: "how many tickets were raised by bolna"
A: {
    "reasoning": "User wants to count tickets raised by organization 'bolna'",
    "intent": "count",
    "organization": "bolna",
    "time_filter": null,
    "query_type": "analytics",
    "filters": {"organization": "bolna"}
}

Q: "top 5 customers"
A: {
    "reasoning": "User wants top 5 organizations ranked by ticket count",
    "intent": "top_n",
    "organization": null,
    "time_filter": null,
    "query_type": "analytics",
    "filters": {"limit": 5}
}

Q: "what issues did Kixie face last month?"
A: {
    "reasoning": "User wants to search for issues faced by Kixie in the last month - semantic search needed",
    "intent": "search",
    "organization": "Kixie",
    "time_filter": "last month",
    "query_type": "lookup",
    "filters": {"organization": "Kixie", "time_period": "last month"}
}

Be precise and extract exact organization names as mentioned by the user."""

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
        plan = {
            "reasoning": analysis.get("reasoning", ""),
            "query_type": analysis.get("query_type", "analytics"),
            "filters": {
                "organization": analysis.get("organization"),
                "time_filter": analysis.get("time_filter")
            },
            "intent": analysis.get("intent", "count"),
            "original_question": question
        }

        logger.info(f"Execution plan: {plan}")
        return plan
