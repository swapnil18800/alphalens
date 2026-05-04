"""
Centralized config for AlphaLens.
All settings read from environment variables via pydantic-settings.
"""
import os
from typing import List, Optional
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────────────
    APP_NAME: str = "AlphaLens"
    APP_TITLE: str = "AlphaLens API"
    APP_DESCRIPTION: str = "Agentic AI equity research — LangGraph RAG over SEC filings & earnings transcripts"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    BASE_URL: str = "http://localhost:8000"
    LOG_LEVEL: str = "INFO"

    # ── Auth ─────────────────────────────────────────────────
    AUTH_DISABLED: bool = True
    CLERK_SECRET_KEY: Optional[str] = None
    CLERK_PUBLISHABLE_KEY: Optional[str] = None

    # ── Database ─────────────────────────────────────────────
    DATABASE_URL: Optional[str] = None
    DB_POOL_MIN: int = 2
    DB_POOL_MAX: int = 10

    # ── LLM ──────────────────────────────────────────────────
    OPENAI_API_KEY: Optional[str] = None
    CEREBRAS_API_KEY: Optional[str] = None
    DEEPSEEK_API_KEY: Optional[str] = None
    LLM_PROVIDER: str = "auto"          # auto | deepseek | cerebras | openai

    # ── Data Sources ─────────────────────────────────────────
    API_NINJAS_KEY: Optional[str] = None
    TAVILY_API_KEY: Optional[str] = None

    # ── Feature flags ────────────────────────────────────────
    CACHE_DISABLED: bool = False   # Set true during eval iteration to avoid stale cache hits

    # ── CORS ─────────────────────────────────────────────────
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173,http://localhost:8000"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
