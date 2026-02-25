"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://postgres:Krishn%4062001@localhost:5433/pdf_management_app"
    sync_database_url: str = "postgresql+psycopg2://postgres:Krishn%4062001@localhost:5433/pdf_management_app"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "your-super-secret-key-change-in-production-minimum-32-chars"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    file_storage_path: str = "./storage"
    max_upload_size_mb: int = 50


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
