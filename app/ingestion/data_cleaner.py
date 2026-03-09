"""Data cleaning and normalization for Zendesk tickets."""

import re
import logging
from datetime import datetime
from typing import Dict, Optional, List, Any

import pandas as pd
from dateutil import parser as date_parser

logger = logging.getLogger(__name__)


class ZendeskDataCleaner:
    """Clean and normalize Zendesk ticket data."""

    # Common email domain to organization name mappings
    DOMAIN_TO_ORG = {
        "gmail.com": None,  # Generic email, use requester name
        "yahoo.com": None,
        "hotmail.com": None,
        "outlook.com": None,
    }

    # Region keywords for classification
    REGION_KEYWORDS = {
        "emea": ["emea", "europe", "middle east", "africa", "uk", "germany", "france"],
        "apac": ["apac", "asia", "pacific", "australia", "singapore", "japan", "india"],
        "americas": ["americas", "usa", "us", "canada", "brazil", "mexico", "north america", "south america"],
    }

    def __init__(self):
        """Initialize data cleaner."""
        self.stats = {
            "total_rows": 0,
            "cleaned_rows": 0,
            "skipped_rows": 0,
            "errors": 0,
        }

    def clean_dataset(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean entire dataset.

        Args:
            df: Raw dataframe from Zendesk export

        Returns:
            Cleaned dataframe
        """
        logger.info(f"Starting data cleaning for {len(df)} rows")
        self.stats["total_rows"] = len(df)

        # Apply cleaning transformations
        df = df.copy()
        df = self._normalize_columns(df)
        df = self._normalize_timestamps(df)
        df = self._normalize_organizations(df)
        df = self._normalize_requesters(df)
        df = self._normalize_tags(df)
        df = self._extract_metadata(df)
        df = self._clean_text_fields(df)

        self.stats["cleaned_rows"] = len(df)
        logger.info(f"Data cleaning complete: {self.stats}")

        return df

    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize column names to snake_case."""
        column_mapping = {
            "Id": "ticket_id",
            "Subject": "subject",
            "Description": "description",
            "Organization": "organization_name",
            "Requester": "requester_name",
            "Requester email": "requester_email",
            "Requester domain": "requester_domain",
            "Assignee": "assignee",
            "Assignee email": "assignee_email",
            "Priority": "priority",
            "Status": "status",
            "Type": "ticket_type",
            "Group": "group_name",
            "Tags": "tags",
            "Created at": "created_at",
            "Updated at": "updated_at",
            "Solved at": "solved_at",
            "Via": "via_channel",
            "Satisfaction score": "satisfaction_score",
            "Country": "country",
            "Country [list]": "country",
            "Area/Region [txt]": "region",
            "Area/Region": "region",
        }

        df = df.rename(columns=column_mapping)
        return df

    def _normalize_timestamps(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize timestamp columns."""
        timestamp_cols = ["created_at", "updated_at", "solved_at"]

        for col in timestamp_cols:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")

        return df

    def _normalize_organizations(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize organization names.

        Strategy:
        1. Use explicit Organization field if available
        2. Derive from requester_domain if domain is not generic
        3. Use requester_name as fallback
        """
        if "organization_name" not in df.columns:
            df["organization_name"] = None

        def resolve_organization(row) -> Optional[str]:
            # Use explicit organization if available
            if pd.notna(row.get("organization_name")) and str(row["organization_name"]).strip():
                return str(row["organization_name"]).strip()

            # Try to derive from email domain
            domain = row.get("requester_domain", "")
            if pd.notna(domain) and domain and domain not in self.DOMAIN_TO_ORG:
                # Extract company name from domain
                org_name = self._extract_org_from_domain(str(domain))
                if org_name:
                    return org_name

            # Fallback to requester name
            requester = row.get("requester_name", "")
            if pd.notna(requester) and requester:
                return str(requester).strip()

            return "Unknown"

        df["organization_name"] = df.apply(resolve_organization, axis=1)
        return df

    def _extract_org_from_domain(self, domain: str) -> Optional[str]:
        """
        Extract organization name from email domain.

        Example: 'kixie.com' -> 'Kixie'
        """
        if not domain or domain in self.DOMAIN_TO_ORG:
            return None

        # Remove TLD and capitalize
        parts = domain.split(".")
        if len(parts) >= 2:
            org_name = parts[0]
            return org_name.capitalize()

        return None

    def _normalize_requesters(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize requester information."""
        # Fill missing requester domains from email
        if "requester_email" in df.columns and "requester_domain" not in df.columns:
            df["requester_domain"] = df["requester_email"].apply(
                lambda email: email.split("@")[1] if pd.notna(email) and "@" in str(email) else None
            )

        # Ensure requester_domain is extracted if missing
        def extract_domain(row):
            if pd.notna(row.get("requester_domain")) and row["requester_domain"]:
                return row["requester_domain"]

            email = row.get("requester_email", "")
            if pd.notna(email) and "@" in str(email):
                return str(email).split("@")[1]

            return None

        if "requester_domain" not in df.columns:
            df["requester_domain"] = None

        df["requester_domain"] = df.apply(extract_domain, axis=1)

        return df

    def _normalize_tags(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize tags into array format."""
        if "tags" not in df.columns:
            df["tags"] = None

        def parse_tags(tags_value) -> List[str]:
            if pd.isna(tags_value) or not tags_value:
                return []

            # Handle space-separated tags
            if isinstance(tags_value, str):
                tags = [tag.strip().lower() for tag in tags_value.split() if tag.strip()]
                return tags

            return []

        df["tags"] = df["tags"].apply(parse_tags)
        return df

    def _extract_metadata(self, df: pd.DataFrame) -> pd.DataFrame:
        """Extract additional metadata fields from tags and other sources."""
        # Extract priority from tags if not in priority field
        def extract_priority(row) -> Optional[str]:
            if pd.notna(row.get("priority")) and row["priority"]:
                return row["priority"]

            tags = row.get("tags", [])
            for tag in tags:
                if tag in ["p1", "p2", "p3", "p4"]:
                    return tag.upper()

            return None

        df["priority"] = df.apply(extract_priority, axis=1)

        # Extract product from tags
        def extract_product(row) -> Optional[str]:
            tags = row.get("tags", [])
            # Look for common product indicators
            product_keywords = ["api", "sdk", "dashboard", "widget", "integration"]
            for tag in tags:
                if any(keyword in tag for keyword in product_keywords):
                    return tag

            return None

        if "product" not in df.columns:
            df["product"] = df.apply(extract_product, axis=1)

        # Extract issue type from tags
        def extract_issue_type(row) -> Optional[str]:
            tags = row.get("tags", [])
            # Common issue type patterns
            issue_types = ["bug", "feature", "question", "incident", "request", "enhancement"]
            for tag in tags:
                if any(itype in tag for itype in issue_types):
                    return tag

            return None

        if "issue_type" not in df.columns:
            df["issue_type"] = df.apply(extract_issue_type, axis=1)

        # Extract region from tags or country
        def extract_region(row) -> Optional[str]:
            # Check tags first
            tags = row.get("tags", [])
            for region, keywords in self.REGION_KEYWORDS.items():
                if any(keyword in " ".join(tags).lower() for keyword in keywords):
                    return region.upper()

            # Check country field
            country = str(row.get("country", "")).lower()
            for region, keywords in self.REGION_KEYWORDS.items():
                if any(keyword in country for keyword in keywords):
                    return region.upper()

            return None

        if "region" not in df.columns:
            df["region"] = None

        df["region"] = df.apply(extract_region, axis=1)

        return df

    def _clean_text_fields(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean text fields (subject, description)."""
        text_fields = ["subject", "description"]

        for field in text_fields:
            if field in df.columns:
                df[field] = df[field].apply(self._clean_text)

        return df

    @staticmethod
    def _clean_text(text: Any) -> Optional[str]:
        """Clean individual text field."""
        if pd.isna(text) or not text:
            return None

        text = str(text)

        # Remove excessive whitespace
        text = re.sub(r"\s+", " ", text)

        # Remove leading/trailing whitespace
        text = text.strip()

        return text if text else None

    def to_dict_records(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Convert dataframe to list of dict records ready for database insertion.

        Args:
            df: Cleaned dataframe

        Returns:
            List of dict records
        """
        # Select only relevant columns for tickets table
        ticket_columns = [
            "ticket_id", "subject", "description", "organization_name",
            "requester_name", "requester_email", "requester_domain",
            "assignee", "assignee_email", "priority", "status", "ticket_type",
            "group_name", "tags", "product", "issue_type", "region", "country",
            "created_at", "updated_at", "solved_at", "via_channel", "satisfaction_score"
        ]

        # Keep only columns that exist
        available_columns = [col for col in ticket_columns if col in df.columns]

        return df[available_columns].to_dict("records")
