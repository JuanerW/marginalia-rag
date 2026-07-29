import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def discard_invalid_ssl_cert_file() -> None:
    """Let Python use its default CA store when an inherited override is stale."""
    cert_file = os.environ.get("SSL_CERT_FILE")
    if cert_file and not Path(cert_file).is_file():
        os.environ.pop("SSL_CERT_FILE", None)


discard_invalid_ssl_cert_file()


class Settings(BaseSettings):
    app_name: str = "Marginalia RAG API"
    api_prefix: str = "/api/v1"
    database_url: str = "postgresql+asyncpg://reader:reader@localhost:5433/reader"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_embedding_model: str = "bge-m3:latest"
    ollama_embedding_timeout_seconds: float = 45
    llm_provider: str = "ollama"
    llm_model: str = "qwen3:4B"
    llm_base_url: str = "http://127.0.0.1:11434"
    llm_api_key: str = ""
    llm_timeout_seconds: float = 90
    ollama_num_ctx: int = 8192
    ollama_num_predict: int = 4096
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
