"""
app/config.py
-------------
Type-safe application configuration and environment settings powered by Pydantic v2.
Enforces configuration validation and separates administrative from read-only DB credentials.
"""

from pathlib import Path
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application configuration and security settings."""
    
    # Application Metadata
    APP_TITLE: str = "Agentic AI Data Analyst - Analytics API"
    APP_VERSION: str = "0.2.0"
    APP_ENV: str = Field(default="development", description="Environment: development, test, production")
    DEBUG: bool = Field(default=False, description="Debug mode")
    
    # Administrative Database Configuration
    DB_HOST: str = Field(default="localhost", description="PostgreSQL host")
    DB_PORT: int = Field(default=5432, description="PostgreSQL port")
    DB_NAME: str = Field(default="agentic_ai_analytics", description="Database name")
    DB_USER: str = Field(default="postgres", description="Administrative DB user")
    DB_PASSWORD: str = Field(default="postgres", description="Administrative DB password")
    
    # SQLAlchemy Connection Strings (Separate Admin vs Read-Only Credentials)
    DATABASE_URL: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/agentic_ai_analytics",
        description="Administrative connection string for migrations and DDL"
    )
    DATABASE_URL_READONLY: str = Field(
        default="postgresql+psycopg://analyst_readonly:analyst_password123@localhost:5432/agentic_ai_analytics",
        description="Restricted read-only connection string for analytical queries"
    )

    # LLM Provider Configuration (OpenAI-compatible)
    LLM_PROVIDER: str = Field(
        default="openai",
        description="LLM Provider: 'openai', 'groq', 'ollama', or 'mock'"
    )
    LLM_API_KEY: Optional[str] = Field(
        default="mock-api-key",
        description="API key for OpenAI-compatible LLM endpoint"
    )
    LLM_BASE_URL: Optional[str] = Field(
        default="https://api.openai.com/v1",
        description="Base URL for OpenAI-compatible LLM API"
    )
    LLM_MODEL: str = Field(
        default="gpt-4o-mini",
        description="LLM model name (e.g. gpt-4o-mini, llama-3.3-70b-versatile, mistral)"
    )
    LLM_TEMPERATURE: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Temperature for deterministic SQL generation (default 0.0)"
    )
    LLM_MAX_TOKENS: int = Field(
        default=1000,
        ge=100,
        le=4000,
        description="Max tokens generated per prompt"
    )

    # Execution & Safety Controls
    QUERY_TIMEOUT_SECONDS: int = Field(
        default=10, 
        description="Maximum execution time (seconds) for analytical queries"
    )
    DEFAULT_ROW_LIMIT: int = Field(
        default=100, 
        description="Default row limit applied to queries"
    )
    MAX_ROW_LIMIT: int = Field(
        default=1000, 
        description="Hard upper ceiling for allowable query row results"
    )
    MAX_REQUEST_BODY_BYTES: int = Field(
        default=1_048_576, # 1 MB
        description="Maximum incoming HTTP request body size in bytes"
    )

    # Security & API Protection
    API_AUTH_ENABLED: bool = Field(default=False, description="Enable API key authentication")
    API_KEY: Optional[str] = Field(default=None, description="Secret API key required for incoming requests")
    RATE_LIMIT_ENABLED: bool = Field(default=False, description="Enable client IP rate limiting")
    RATE_LIMIT_PER_MINUTE: int = Field(default=60, description="Max requests permitted per minute per IP")

    # Service & Dashboard URLs
    BACKEND_URL: str = Field(default="http://localhost:8000", description="Backend FastAPI service URL")

    # Connection Pooling Parameters
    DB_POOL_SIZE: int = Field(default=10, description="SQLAlchemy connection pool size")
    DB_MAX_OVERFLOW: int = Field(default=20, description="SQLAlchemy connection pool max overflow")
    DB_POOL_TIMEOUT: int = Field(default=30, description="Seconds to wait before giving up on a pool connection")
    DB_POOL_RECYCLE: int = Field(default=1800, description="Recycle connections older than N seconds")

    # Configuration Validation
    @field_validator("DB_PORT")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not (1 <= v <= 65535):
            raise ValueError(f"DB_PORT must be between 1 and 65535, got {v}")
        return v

    @field_validator("QUERY_TIMEOUT_SECONDS")
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        if not (1 <= v <= 120):
            raise ValueError(f"QUERY_TIMEOUT_SECONDS must be between 1 and 120 seconds, got {v}")
        return v

    @field_validator("MAX_ROW_LIMIT")
    @classmethod
    def validate_max_row_limit(cls, v: int, info) -> int:
        if v < 1:
            raise ValueError(f"MAX_ROW_LIMIT must be >= 1, got {v}")
        return v

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )


# Global settings singleton
settings = Settings()
