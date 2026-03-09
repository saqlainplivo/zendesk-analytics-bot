"""CSV data loader for Zendesk tickets."""

import logging
from pathlib import Path
from typing import List, Dict, Any

import pandas as pd
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.database.models import Ticket
from app.ingestion.data_cleaner import ZendeskDataCleaner

logger = logging.getLogger(__name__)


class CSVLoader:
    """Load Zendesk tickets from CSV file into database."""

    def __init__(self, csv_path: str):
        """
        Initialize CSV loader.

        Args:
            csv_path: Path to Zendesk CSV export file
        """
        self.csv_path = Path(csv_path)
        self.cleaner = ZendeskDataCleaner()

        if not self.csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

    def load(self, db: Session, batch_size: int = 100) -> int:
        """
        Load tickets from CSV into database.

        Args:
            db: Database session
            batch_size: Number of records to insert per batch

        Returns:
            Number of tickets loaded
        """
        logger.info(f"Loading tickets from {self.csv_path}")

        # Read CSV
        try:
            df = pd.read_csv(self.csv_path)
            logger.info(f"Read {len(df)} rows from CSV")
        except Exception as e:
            logger.error(f"Failed to read CSV: {e}")
            raise

        # Clean data
        df_cleaned = self.cleaner.clean_dataset(df)
        logger.info(f"Cleaned data: {len(df_cleaned)} rows")

        # Convert to dict records
        records = self.cleaner.to_dict_records(df_cleaned)

        # Insert into database in batches
        total_inserted = 0
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            inserted = self._insert_batch(db, batch)
            total_inserted += inserted
            logger.info(f"Inserted batch {i//batch_size + 1}: {inserted} records (total: {total_inserted})")

        logger.info(f"Successfully loaded {total_inserted} tickets")
        return total_inserted

    def _insert_batch(self, db: Session, records: List[Dict[str, Any]]) -> int:
        """
        Insert batch of records using upsert logic.

        Args:
            db: Database session
            records: List of ticket records

        Returns:
            Number of records inserted/updated
        """
        try:
            # Use PostgreSQL upsert (ON CONFLICT DO UPDATE)
            stmt = insert(Ticket).values(records)
            stmt = stmt.on_conflict_do_update(
                index_elements=["ticket_id"],
                set_={
                    "subject": stmt.excluded.subject,
                    "description": stmt.excluded.description,
                    "organization_name": stmt.excluded.organization_name,
                    "requester_name": stmt.excluded.requester_name,
                    "requester_email": stmt.excluded.requester_email,
                    "requester_domain": stmt.excluded.requester_domain,
                    "assignee": stmt.excluded.assignee,
                    "assignee_email": stmt.excluded.assignee_email,
                    "priority": stmt.excluded.priority,
                    "status": stmt.excluded.status,
                    "ticket_type": stmt.excluded.ticket_type,
                    "group_name": stmt.excluded.group_name,
                    "tags": stmt.excluded.tags,
                    "product": stmt.excluded.product,
                    "issue_type": stmt.excluded.issue_type,
                    "region": stmt.excluded.region,
                    "country": stmt.excluded.country,
                    "updated_at": stmt.excluded.updated_at,
                    "solved_at": stmt.excluded.solved_at,
                    "via_channel": stmt.excluded.via_channel,
                    "satisfaction_score": stmt.excluded.satisfaction_score,
                }
            )

            db.execute(stmt)
            db.commit()

            return len(records)
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to insert batch: {e}")
            raise

    def get_stats(self) -> Dict[str, Any]:
        """Get loader statistics."""
        return {
            "csv_path": str(self.csv_path),
            "cleaner_stats": self.cleaner.stats,
        }
