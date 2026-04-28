from __future__ import annotations

import logging
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration loaded from .env file and environment variables."""

    database_url: str = "postgresql+asyncpg://piratehunt:piratehunt@localhost:5432/piratehunt"
    redis_url: str = "redis://localhost:6379"
    faiss_index_path: str | Path = Path("./data/visual_index.faiss")
    log_level: str = "INFO"

    # Gemini API
    gemini_api_key: str | None = None

    # DMCA settings
    dmca_default_language: str = "en"
    dmca_gemini_polish_enabled: bool = True
    dmca_generation_timeout_seconds: int = 30
    redis_takedowns_stream: str = "piratehunt:takedowns"
    dmca_default_rights_holder_id: str | None = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


settings = Settings()

# Configure logging
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
