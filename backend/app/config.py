from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(value: str) -> str:
    """Accept the URI copied from Supabase and make it usable by SQLAlchemy."""
    if value.startswith("sqlite"):
        return value
    if value.startswith("postgres://"):
        value = "postgresql://" + value[len("postgres://") :]
    if value.startswith("postgresql://"):
        value = "postgresql+psycopg2://" + value[len("postgresql://") :]
    if ("supabase.com" in value or "supabase.co" in value) and "sslmode=" not in value:
        separator = "&" if "?" in value else "?"
        value = f"{value}{separator}sslmode=require"
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    dev_mode: bool = True
    database_url: str = "postgresql+psycopg2://email:email@localhost:5432/email_classifier"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "dev-only-change-me"
    encryption_key: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"
    frontend_url: str = "http://localhost:5173"
    retention_days: int = 365
    fetch_interval_seconds: int = 300
    model_path: str = "models/classifier.joblib"
    gmail_scopes: str = "https://www.googleapis.com/auth/gmail.readonly"

    @field_validator("database_url")
    @classmethod
    def use_supabase_driver(cls, value: str) -> str:
        return normalize_database_url(value)


@lru_cache
def get_settings() -> Settings:
    return Settings()
