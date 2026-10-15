"""Application settings and configuration management using Pydantic Settings."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.utils.exceptions import ConfigurationError

# Base directory for the repository
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Strongly typed application configuration settings."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Google Gemini AI Configuration
    GEMINI_API_KEY: Optional[str] = Field(default=None, description="Google Gemini API Key")
    GEMINI_MODEL: str = Field(default="gemini-3.8-flash", description="Gemini model identifier")

    # PostgreSQL Database Configuration
    DATABASE_URL: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/ecommerce_analytics",
        description="SQLAlchemy database connection string",
    )
    DB_POOL_SIZE: int = Field(default=10, description="Database connection pool size")
    DB_MAX_OVERFLOW: int = Field(default=20, description="Database connection max overflow")
    DB_POOL_TIMEOUT: int = Field(default=30, description="Database connection pool timeout in seconds")

    # Application Environment
    APP_ENV: str = Field(default="development", description="Environment: development, staging, production")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL")
    APP_HOST: str = Field(default="0.0.0.0", description="Streamlit host binding")
    APP_PORT: int = Field(default=8501, description="Streamlit port")

    # Machine Learning and Churn Configuration
    CHURN_HORIZON_DAYS: int = Field(default=90, description="Days without purchase to define customer churn")
    FEATURE_LOOKBACK_DAYS: int = Field(default=365, description="Lookback days for historical feature computation")
    MIN_ORDERS_FOR_CHURN: int = Field(default=1, description="Minimum qualifying orders required before churn observation")
    RANDOM_SEED: int = Field(default=42, description="Random seed for model reproducibility")
    CHURN_DECISION_THRESHOLD: float = Field(default=0.50, description="Classification probability threshold")

    # Ingestion and Path Directories
    BATCH_SIZE: int = Field(default=5000, description="Batch size for database insertions")
    DATA_RAW_DIR: Path = Field(default=BASE_DIR / "data" / "raw")
    DATA_PROCESSED_DIR: Path = Field(default=BASE_DIR / "data" / "processed")
    ARTIFACTS_DIR: Path = Field(default=BASE_DIR / "artifacts")
    LOGS_DIR: Path = Field(default=BASE_DIR / "logs")

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        valid_prefixes = ("postgresql://", "postgresql+psycopg2://", "sqlite:///", "sqlite://")
        if not v or not any(v.startswith(prefix) for prefix in valid_prefixes):
            raise ValueError("DATABASE_URL must be a valid PostgreSQL or SQLite connection string.")
        return v

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"

    def validate_for_llm(self) -> None:
        """Validate that LLM credentials are present without printing secret contents."""
        if not self.GEMINI_API_KEY or self.GEMINI_API_KEY.strip() in ("", "your_gemini_api_key_here"):
            raise ConfigurationError(
                "GEMINI_API_KEY is not configured. Please set a valid API key in your environment or .env file."
            )

    def safe_dict(self) -> dict:
        """Export settings dictionary with masked credentials for safe logging and debugging."""
        d = self.model_dump()
        if d.get("GEMINI_API_KEY"):
            masked_key = d["GEMINI_API_KEY"][:4] + "..." + d["GEMINI_API_KEY"][-4:] if len(d["GEMINI_API_KEY"]) > 8 else "***"
            d["GEMINI_API_KEY"] = masked_key
        if d.get("DATABASE_URL"):
            # Mask DB password if present
            url = d["DATABASE_URL"]
            if "@" in url and ":" in url:
                parts = url.split("@")
                user_pass = parts[0].split("://")[-1]
                if ":" in user_pass:
                    user = user_pass.split(":")[0]
                    d["DATABASE_URL"] = f"postgresql://{user}:***@{parts[1]}"
        return d


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached singleton application settings instance."""
    return Settings()
