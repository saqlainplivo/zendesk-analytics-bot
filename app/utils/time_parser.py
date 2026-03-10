"""Time expression parser for natural language queries."""

import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple
import re

logger = logging.getLogger(__name__)


class TimeParser:
    """Parse natural language time expressions."""

    @staticmethod
    def parse_time_filter(text: str) -> Optional[Tuple[datetime, datetime]]:
        """
        Parse time filter from text.

        Args:
            text: Natural language text containing time expression

        Returns:
            Tuple of (start_date, end_date) or None
        """
        text_lower = text.lower()
        now = datetime.now()

        # Today
        if any(word in text_lower for word in ["today", "today's"]):
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return (start, now)

        # Yesterday
        if "yesterday" in text_lower:
            yesterday = now - timedelta(days=1)
            start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            end = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
            return (start, end)

        # This week
        if "this week" in text_lower:
            days_since_monday = now.weekday()
            start = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
            return (start, now)

        # Last week
        if "last week" in text_lower:
            days_since_monday = now.weekday()
            this_monday = now - timedelta(days=days_since_monday)
            last_monday = this_monday - timedelta(days=7)
            last_sunday = last_monday + timedelta(days=6, hours=23, minutes=59, seconds=59)
            start = last_monday.replace(hour=0, minute=0, second=0, microsecond=0)
            return (start, last_sunday)

        # This month
        if "this month" in text_lower:
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            return (start, now)

        # Last month
        if "last month" in text_lower:
            # Get first day of current month, then go back one month
            first_of_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            last_month_end = first_of_this_month - timedelta(days=1)
            start = last_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end = last_month_end.replace(hour=23, minute=59, second=59, microsecond=999999)
            return (start, end)

        # Last N days
        last_days_match = re.search(r'last\s+(\d+)\s+days?', text_lower)
        if last_days_match:
            days = int(last_days_match.group(1))
            start = now - timedelta(days=days)
            return (start, now)

        # Last 7 days (common)
        if any(phrase in text_lower for phrase in ["last 7 days", "past 7 days", "past week"]):
            start = now - timedelta(days=7)
            return (start, now)

        # Last 30 days
        if any(phrase in text_lower for phrase in ["last 30 days", "past 30 days", "past month"]):
            start = now - timedelta(days=30)
            return (start, now)

        # Recent (default to last 7 days)
        if "recent" in text_lower:
            start = now - timedelta(days=7)
            return (start, now)

        return None

    @staticmethod
    def format_time_range(start: datetime, end: datetime) -> str:
        """Format time range for display."""
        if start.date() == end.date():
            return f"on {start.strftime('%B %d, %Y')}"
        else:
            return f"from {start.strftime('%B %d, %Y')} to {end.strftime('%B %d, %Y')}"
