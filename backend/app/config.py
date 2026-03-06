from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://agents:agents_secret_2026@localhost:4532/ai_agents"
    REDIS_URL: str = "redis://:redis_secret_2026@localhost:4379/0"
    CHROMADB_URL: str = "http://localhost:4800"

    # JWT
    JWT_SECRET_KEY: str = "super-secret-jwt-key-change-in-production-2026"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Default admin
    DEFAULT_ADMIN_USERNAME: str = "admin"
    DEFAULT_ADMIN_PASSWORD: str = "admin123"

    # Ollama
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # App
    APP_TITLE: str = "AI Agents Server"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True
    CORS_ORIGINS: list[str] = ["http://localhost:4200", "http://localhost:4700"]

    # Skills
    SKILLS_DIR: str = "./data/skills"

    # Agents
    AGENTS_DIR: str = "./data/agents"

    # Projects (code storage for agents)
    PROJECTS_DIR: str = "../data/projects"

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
