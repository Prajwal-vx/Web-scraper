from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field
import os

class Settings(BaseSettings):
    APP_NAME: str = "NEXUS SCRAPE AI"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "production"
    DEBUG: bool = False

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # Database (Default SQLite for standalone ease, PostgreSQL in docker)
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./nexus_scrape.db")
    
    # Redis / Celery (Optional, fallback to in-memory async runner)
    REDIS_URL: Optional[str] = os.getenv("REDIS_URL", None)

    # Security & JWT
    SECRET_KEY: str = os.getenv("SECRET_KEY", "nexus-scrape-production-secret-key-change-me-32b")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    ALLOWED_ORIGINS: List[str] = ["*"]
    
    # Scraper & Crawl Limits
    MAX_RESPONSE_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB limit
    DEFAULT_CRAWL_DELAY_SECONDS: float = 1.0
    DEFAULT_MAX_CONCURRENT_JOBS: int = 4
    MAX_PAGES_HARD_LIMIT: int = 500
    REQUEST_TIMEOUT_SECONDS: int = 15
    USER_AGENT: str = "NexusScrapeAI/1.0 (+https://nexusscrape.ai/bot; polite-crawler)"

    # Browser Worker (Playwright)
    PLAYWRIGHT_ENABLED: bool = True
    PLAYWRIGHT_TIMEOUT_SECONDS: int = 20

    # AI Extraction Assistants (Pluggable)
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "heuristic")  # "heuristic", "openai", "gemini", "anthropic"
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY", None)
    ANTHROPIC_API_KEY: Optional[str] = os.getenv("ANTHROPIC_API_KEY", None)
    GEMINI_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY", None)
    AI_MODEL_NAME: str = os.getenv("AI_MODEL_NAME", "gpt-4o-mini")

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
