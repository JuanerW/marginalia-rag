from dataclasses import dataclass

from langchain_core.language_models.chat_models import BaseChatModel

from src.core.config import settings


class ChatModelConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class ChatModelConfig:
    provider: str
    model: str
    base_url: str = ""
    api_key: str = ""


def current_chat_config(model_override: str | None = None) -> ChatModelConfig:
    provider = settings.llm_provider.strip().lower()
    base_url = settings.llm_base_url
    api_key = settings.llm_api_key or settings.openai_api_key
    if provider == "ollama":
        base_url = base_url or settings.ollama_url
    return ChatModelConfig(
        provider=provider,
        model=model_override or settings.llm_model,
        base_url=base_url,
        api_key=api_key,
    )


def create_chat_model(config: ChatModelConfig) -> BaseChatModel:
    if config.provider == "ollama":
        from langchain_ollama import ChatOllama

        if not config.base_url:
            raise ChatModelConfigurationError("Ollama 需要配置 LLM_BASE_URL")
        return ChatOllama(
            model=config.model,
            base_url=config.base_url,
            temperature=0.2,
            reasoning=True,
            num_ctx=settings.ollama_num_ctx,
            num_predict=settings.ollama_num_predict,
            client_kwargs={"timeout": settings.llm_timeout_seconds},
        )
    if config.provider == "openai":
        from langchain_openai import ChatOpenAI

        if not config.api_key:
            raise ChatModelConfigurationError("OpenAI 需要配置 LLM_API_KEY")
        return ChatOpenAI(
            model=config.model,
            api_key=config.api_key,
            temperature=0.2,
            timeout=300,
            max_retries=2,
        )
    if config.provider == "openai_compatible":
        from langchain_openai import ChatOpenAI

        if not config.base_url or not config.api_key:
            raise ChatModelConfigurationError(
                "OpenAI-compatible API 需要配置 LLM_BASE_URL 和 LLM_API_KEY"
            )
        return ChatOpenAI(
            model=config.model,
            api_key=config.api_key,
            base_url=config.base_url,
            temperature=0.2,
            timeout=300,
            max_retries=2,
        )
    raise ChatModelConfigurationError(
        "LLM_PROVIDER 仅支持 ollama、openai 或 openai_compatible"
    )
