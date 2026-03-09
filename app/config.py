"""Application configuration management."""

from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # OpenAI
    openai_api_key: str
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 1536
    llm_model: str = "gpt-4-turbo-preview"
    llm_temperature: float = 0.0

    # Supabase (primary database connection)
    supabase_url: str
    supabase_anon_key: str

    # Database (optional - for direct PostgreSQL if needed)
    database_url: Optional[str] = None
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "zendesk_analytics"
    db_user: str = "postgres"
    db_password: str = "password"

    # Application
    app_env: str = "development"
    log_level: str = "INFO"

    # Vector Search
    top_k_results: int = 5
    similarity_threshold: float = 0.7

    # Data Source
    zendesk_csv_path: str = "../Zendesk_tix.csv"

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.app_env.lower() == "production"

    @property
    def database_url_sync(self) -> str:
        """Get synchronous database URL."""
        if self.database_url:
            return self.database_url.replace("+asyncpg", "").replace("postgresql://", "postgresql://")
        # Construct from Supabase or other credentials
        # For now, we're using Supabase REST API, so we construct a dummy URL
        # or use db credentials if available
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"


# Global settings instance
settings = Settings()
