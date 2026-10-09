"""
GeoMeasureX - Application Configuration

Centralized configuration using pydantic-settings for type-safe
environment variable handling. Supports .env files for local development
and environment variables for production/Docker deployments.
"""

from pathlib import Path
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ── Environment ──────────────────────────────────────────────
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"

    # ── Database ─────────────────────────────────────────────────
    DATABASE_URL: str = "sqlite:///./geomeasurex.db"

    # ── File Upload ──────────────────────────────────────────────
    MAX_UPLOAD_SIZE_MB: int = 50
    TEMP_DIRECTORY: str = "./temp"
    UPLOAD_DIRECTORY: str = "./uploads"

    # ── Logging ──────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"

    # ── API ──────────────────────────────────────────────────────
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # ── Frontend (CORS) ─────────────────────────────────────────
    FRONTEND_URL: str = "http://localhost:5173"

    # ── Measurement Precision ────────────────────────────────────
    # Internal computation precision (decimal places stored)
    MEASUREMENT_DECIMAL_PLACES: int = 6
    # API response display precision
    API_DISPLAY_DECIMAL_PLACES: int = 2

    # ── Derived Properties ───────────────────────────────────────
    @property
    def max_upload_size_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @property
    def temp_path(self) -> Path:
        path = Path(self.TEMP_DIRECTORY)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def upload_path(self) -> Path:
        path = Path(self.UPLOAD_DIRECTORY)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


@lru_cache()
def get_settings() -> Settings:
    """Cached settings singleton. Use dependency injection in FastAPI."""
    return Settings()
