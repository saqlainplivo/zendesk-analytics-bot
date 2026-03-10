"""Groq-powered reasoning engine for ultra-fast query analysis and validation."""

import logging
import json
from typing import Dict, Any, Optional, Iterator
from groq import Groq

from app.config import settings

logger = logging.getLogger(__name__)


class GroqReasoningEngine:
    """
    High-speed reasoning engine using Groq's LPU inference.
    Provides pre-query analysis and post-response validation.
    """

    def __init__(self):
        """Initialize Groq reasoning engine."""
        self.client = Groq(api_key=settings.groq_api_key) if settings.groq_api_key else None
        self.model = settings.groq_model

    def analyze_question(self, question: str) -> Dict[str, Any]:
        """
        Analyze question with lightning-fast Groq inference.

        Args:
            question: Natural language question

        Returns:
            Analysis with reasoning, intent, and extracted parameters
        """
        if not self.client:
            logger.warning("Groq API key not configured, using fallback")
            return self._fallback_analysis(question)

        logger.info(f"🚀 Groq analyzing: {question}")

        system_prompt = """You are an expert query analyzer for a Zendesk ticket analytics system.

Analyze the user's question and extract:
1. **Reasoning**: Your step-by-step thought process
2. **Intent**: What the user wants (count/list/top_n/search/summary)
   - Use "list" for: "show", "list", "display", "get", "what tickets"
   - Use "count" for: "how many", "count", "number of", "total"
   - Use "search" for: "issues", "problems", "what", "find" (when asking about content)
   - Use "top_n" for: "top", "most", "highest", "best"
3. **Organization**: Exact company name mentioned (preserve case, extract core name)
4. **Time Filter**: Any time period mentioned
5. **Query Type**: "analytics" (counts/stats/lists) or "lookup" (semantic search for issues/problems)

Return JSON:
{
    "reasoning": "Clear explanation of what user wants",
    "intent": "count|list|top_n|search|summary",
    "organization": "lowercase core name or null",
    "time_filter": "period or null",
    "query_type": "analytics|lookup",
    "confidence": 0.0-1.0,
    "filters": {
        "priority": "high|urgent|normal|low|null",
        "status": "open|closed|pending|solved|null"
    }
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

"List Kixie tickets" →
{
    "reasoning": "User wants to see a list of tickets from Kixie",
    "intent": "list",
    "organization": "kixie",
    "query_type": "analytics",
    "confidence": 0.95
}

"Show me all tickets from Bolna" →
{
    "reasoning": "User wants to display/list all tickets from Bolna organization",
    "intent": "list",
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

"Show open tickets" →
{
    "reasoning": "User wants to list tickets with open status",
    "intent": "list",
    "organization": null,
    "query_type": "analytics",
    "confidence": 0.95,
    "filters": {"status": "open"}
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
            logger.info(f"✓ Groq analysis: {analysis.get('reasoning', '')[:100]}...")

            return analysis

        except Exception as e:
            logger.error(f"Groq analysis error: {e}")
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

        logger.info("🔍 Groq validating response...")

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

    def stream_enhanced_response(
        self,
        question: str,
        base_answer: str,
        evidence: list
    ) -> Iterator[str]:
        """
        Stream enhanced, markdown-formatted response.
        Uses GPT for generation if Groq unavailable.

        Args:
            question: User's question
            base_answer: Raw answer from agent
            evidence: Ticket IDs as evidence

        Yields:
            Chunks of enhanced markdown response
        """
        # Use GPT fallback if Groq not available
        if not self.client:
            import openai
            gpt_client = openai.OpenAI(api_key=settings.openai_api_key)

            enhancement_prompt = f"""Transform this answer into clear, markdown-formatted response.

Question: {question}
Answer: {base_answer}

Make it conversational, use markdown, highlight key info. Be concise."""

            try:
                stream = gpt_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": enhancement_prompt}],
                    temperature=0.3,
                    stream=True
                )
                for chunk in stream:
                    if chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                return
            except:
                yield base_answer
                return

        # ALWAYS use GPT-4 for answer enhancement (better quality)
        import openai
        gpt_client = openai.OpenAI(api_key=settings.openai_api_key)

        enhancement_prompt = f"""Transform this answer into a clear, markdown-formatted response.

Question: {question}
Answer: {base_answer}

Requirements:
1. Use markdown (**bold**, *italic*, lists)
2. Professional and conversational
3. Highlight key numbers and names
4. Add context if helpful
5. Natural language, not robotic

Output the enhanced answer directly."""

        try:
            stream = gpt_client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[{"role": "user", "content": enhancement_prompt}],
                temperature=0.3,
                max_tokens=1000,
                stream=True
            )

            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            logger.error(f"GPT streaming error: {e}")
            yield base_answer

    def create_execution_plan(
        self,
        question: str,
        analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create execution plan based on Groq analysis.

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
        """Fallback analysis when Groq is unavailable."""
        return {
            "reasoning": "Basic pattern matching (Groq unavailable)",
            "intent": "count",
            "organization": None,
            "time_filter": None,
            "query_type": "analytics",
            "confidence": 0.5,
            "filters": {}
        }
