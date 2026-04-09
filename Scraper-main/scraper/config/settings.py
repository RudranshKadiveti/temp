import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Distributed Scraper Platform"
    
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    POSTGRES_URL: str = os.getenv("POSTGRES_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/scraper")
    ELASTICSEARCH_URL: str = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
    
    HTML_STORAGE_PATH: str = os.getenv("HTML_STORAGE_PATH", "./data/raw_html")
    
    CONCURRENCY: int = int(os.getenv("CONCURRENCY", "100"))
    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "30"))
    RETRY_COUNT: int = int(os.getenv("RETRY_COUNT", "3"))
    USER_AGENT_ROTATION_ENABLED: bool = True
    
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
