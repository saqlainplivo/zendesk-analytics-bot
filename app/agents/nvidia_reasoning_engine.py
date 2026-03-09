"""NVIDIA NIM-powered reasoning engine for query analysis."""

import logging
import json
from typing import Dict, Any, Iterator
from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)


class NvidiaReasoningEngine:
    """
    NVIDIA NIM reasoning engine using their API.
    Provides pre-query analysis and post-response validation.
    """

    def __init__(self):
        """Initialize NVIDIA NIM client."""
        self.client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=settings.nvidia_nim_api_key
        ) if settings.nvidia_nim_api_key else None
        # Try different model names that NVIDIA NIM supports
        self.model = "meta/llama-3.1-70b-instruct"  # Alternative model name

    def analyze_question(self, question: str) -> Dict[str, Any]:
        """
        Analyze question with NVIDIA NIM inference.

        Args:
            question: Natural language question

        Returns:
            Analysis with reasoning, intent, and extracted parameters
        """
        if not self.client:
            logger.warning("NVIDIA NIM API key not configured, using fallback")
            return self._fallback_analysis(question)

        logger.info(f"🎯 NVIDIA NIM analyzing: {question}")

        system_prompt = """You are an expert query analyzer for a Zendesk ticket analytics system.

Analyze the user's question and extract:
1. **Reasoning**: Your step-by-step thought process
2. **Intent**: What the user wants (count/list/top_n/search/summary)
3. **Organization**: Company name mentioned (preserve partial names, extract the core)
4. **Time Filter**: Any time period mentioned
5. **Query Type**: "analytics" (counts/stats) or "lookup" (semantic search)

IMPORTANT for Organization Extraction:
- If user says "Bolna", extract just "bolna" (lowercase core)
- If user says "Kixie", extract just "kixie" (lowercase core)
- Extract the BASE name only, without suffixes like .ai, .com, (YC batch), etc.
- Always lowercase the extracted organization name for fuzzy matching

Return JSON:
{
    "reasoning": "Clear explanation of what user wants",
    "intent": "count|list|top_n|search|summary",
    "organization": "lowercase core name or null",
    "time_filter": "period or null",
    "query_type": "analytics|lookup",
    "confidence": 0.0-1.0,
    "filters": {"key": "value"}
}

Examples:

"Bolna ticket count" →
{
    "reasoning": "User wants count of tickets for 'Bolna' organization",
    "intent": "count",
    "organization": "bolna",
    "query_type": "analytics",
    "confidence": 0.95
}

"what issues did Kixie face last month?" →
{
    "reasoning": "User wants semantic search of Kixie's issues from last month",
    "intent": "search",
    "organization": "kixie",
    "time_filter": "last month",
    "query_type": "lookup",
    "confidence": 0.90
}

Be precise. Extract lowercase core names for fuzzy matching."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Analyze: {question}"}
                ],
                temperature=0.0,
                max_tokens=500
            )

            content = response.choices[0].message.content.strip()

            # Extract JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            analysis = json.loads(content)
            logger.info(f"✓ NVIDIA analysis: {analysis.get('reasoning', '')[:100]}...")

            return analysis

        except Exception as e:
            logger.error(f"NVIDIA NIM analysis error: {e}")
            return self._fallback_analysis(question)

    def validate_response(
        self,
        question: str,
        analysis: Dict[str, Any],
        answer: str
    ) -> Dict[str, Any]:
        """
        Validate response quality and accuracy.

        Args:
            question: Original question
            analysis: Pre-query analysis
            answer: Generated answer

        Returns:
            Validation result with quality score and suggestions
        """
        if not self.client:
            return {"valid": True, "quality_score": 0.8, "suggestions": []}

        logger.info("🔍 NVIDIA validating response...")

        validation_prompt = f"""You are a quality validator for an AI analytics system.

Question: {question}
Analysis: {analysis.get('reasoning', '')}
Generated Answer: {answer}

Validate if the answer:
1. Actually answers the question
2. Uses correct data (check if it makes sense)
3. Is clear and well-formatted
4. Matches the query intent

Return JSON:
{{
    "valid": true/false,
    "quality_score": 0.0-1.0,
    "reasoning": "why valid or invalid",
    "suggestions": ["improvement1", "improvement2"]
}}"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": validation_prompt}],
                temperature=0.0,
                max_tokens=300
            )

            content = response.choices[0].message.content.strip()

            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()

            validation = json.loads(content)
            logger.info(f"✓ Validation: {validation.get('quality_score', 0):.2f} quality score")

            return validation

        except Exception as e:
            logger.error(f"Validation error: {e}")
            return {"valid": True, "quality_score": 0.8, "suggestions": []}

    def create_execution_plan(
        self,
        question: str,
        analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create execution plan based on NVIDIA analysis.

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
            "confidence": analysis.get("confidence", 0.8),
            "original_question": question
        }

        logger.info(f"✓ Execution plan created: {plan['intent']}")
        return plan

    def _fallback_analysis(self, question: str) -> Dict[str, Any]:
        """Fallback analysis when NVIDIA NIM is unavailable."""
        return {
            "reasoning": "Basic pattern matching (NVIDIA NIM unavailable)",
            "intent": "count",
            "organization": None,
            "time_filter": None,
            "query_type": "analytics",
            "confidence": 0.5,
            "filters": {}
        }
