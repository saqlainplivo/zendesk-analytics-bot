"""Database connection and session management."""

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from sqlalchemy.pool import QueuePool

from app.config import settings

logger = logging.getLogger(__name__)

# SQLAlchemy Base
Base = declarative_base()

# Create engine with connection pooling
# Add SSL parameters for cloud databases like Supabase
try:
    connect_args = {}
    if settings.database_url and ("supabase" in settings.database_url_sync or "?sslmode=" in settings.database_url_sync):
        connect_args = {
            "sslmode": "require",
            "connect_timeout": 10,
        }

    engine = create_engine(
        settings.database_url_sync,
        poolclass=QueuePool,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,  # Verify connections before using
        echo=settings.log_level == "DEBUG",
        connect_args=connect_args,
    )

    # Session factory
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    logger.info("Database engine created successfully")
except Exception as e:
    logger.warning(f"Database engine creation failed: {e}")
    logger.warning("Server will start but database operations will fail")
    # Create a dummy engine to allow imports
    engine = None
    SessionLocal = None


def get_db() -> Generator[Session, None, None]:
    """
    Get database session for dependency injection.

    Usage in FastAPI:
        @app.get("/endpoint")
        def endpoint(db: Session = Depends(get_db)):
            ...
    """
    if SessionLocal is None:
        logger.error("Database not available")
        yield None
        return

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Get database session as context manager.

    Usage:
        with get_db_session() as db:
            result = db.execute(query)
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        db.close()


def init_db() -> None:
    """Initialize database with schema."""
    logger.info("Initializing database...")

    # Read and execute schema.sql
    schema_path = "app/database/schema.sql"
    try:
        with open(schema_path, "r") as f:
            schema_sql = f.read()

        with engine.begin() as conn:
            # Execute each statement separately
            for statement in schema_sql.split(";"):
                statement = statement.strip()
                if statement:
                    conn.execute(text(statement))

        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


def check_db_connection() -> bool:
    """Check if database connection is working."""
    if engine is None:
        logger.error("Database engine not initialized")
        return False

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection successful")
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False


def check_pgvector_extension() -> bool:
    """Check if pgvector extension is installed."""
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
            )
            installed = result.fetchone() is not None

        if installed:
            logger.info("pgvector extension is installed")
        else:
            logger.warning("pgvector extension is NOT installed")

        return installed
    except Exception as e:
        logger.error(f"Failed to check pgvector extension: {e}")
        return False
