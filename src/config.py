"""
src/config.py
-------------
Centralized application configuration managed through Pydantic Settings.
Reads environment variables from .env file with safe defaults.
"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application configuration and security parameters."""
    
    # PostgreSQL Configuration
    DB_HOST: str = Field(default="localhost", description="PostgreSQL host")
    DB_PORT: int = Field(default=5432, description="PostgreSQL port")
    DB_NAME: str = Field(default="agentic_ai_analytics", description="Database name")
    DB_USER: str = Field(default="postgres", description="Admin database user")
    DB_PASSWORD: str = Field(default="postgres", description="Admin database password")
    
    # SQLAlchemy Connection Strings
    DATABASE_URL: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/agentic_ai_analytics",
        description="Admin connection URL for migrations and data loading"
    )
    DATABASE_URL_READONLY: str = Field(
        default="postgresql+psycopg://analyst_readonly:analyst_password123@localhost:5432/agentic_ai_analytics",
        description="Restricted read-only connection URL for AI agent query execution"
    )
    
    # Synthetic Data Parameters
    RANDOM_SEED: int = Field(default=42, description="Fixed random seed for reproducible synthetic data")
    NUM_CUSTOMERS: int = Field(default=500, description="Minimum synthetic customer count")
    NUM_PRODUCTS: int = Field(default=25, description="Synthetic product count")
    NUM_STORES: int = Field(default=9, description="Synthetic store count")
    NUM_ORDERS: int = Field(default=2200, description="Synthetic order count")
    
    # Safety Limits
    QUERY_TIMEOUT_SECONDS: int = Field(default=10, description="Max execution time per SQL query")
    DEFAULT_ROW_LIMIT: int = Field(default=100, description="Default safety row limit")
    MAX_ROW_LIMIT: int = Field(default=1000, description="Maximum allowable row limit")

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )


# Global singleton settings instance
settings = Settings()
