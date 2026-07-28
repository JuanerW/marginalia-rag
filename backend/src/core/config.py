from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Marginalia RAG API"
    api_prefix: str = "/api/v1"
    database_url: str = "postgresql+asyncpg://reader:reader@localhost:5433/reader"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_embedding_model: str = "bge-m3:latest"
    cors_origins: list[str] = ["http://localhost:5173"]

    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
