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
    extra_body: dict[str, object] | None = None


@dataclass(frozen=True)
class ChatModelOption:
    id: str
    label: str
    provider: str
    model: str
    available: bool
    is_default: bool


def chat_model_options() -> list[ChatModelOption]:
    default_id = settings.llm_provider.strip().lower()
    if default_id not in {"ollama", "qwen", "deepseek"}:
        default_id = "ollama"
    return [
        ChatModelOption(
            id="ollama",
            label="本地 Qwen",
            provider="Ollama",
            model=settings.llm_model,
            available=True,
            is_default=default_id == "ollama",
        ),
        ChatModelOption(
            id="qwen",
            label="云端 Qwen",
            provider="阿里云百炼",
            model=settings.qwen_chat_model,
            available=bool(settings.qwen_api_key),
            is_default=default_id == "qwen",
        ),
        ChatModelOption(
            id="deepseek",
            label="DeepSeek",
            provider="DeepSeek API",
            model=settings.deepseek_chat_model,
            available=bool(settings.deepseek_api_key),
            is_default=default_id == "deepseek",
        ),
    ]


def current_chat_config(
    model_override: str | None = None,
    profile_id: str | None = None,
) -> ChatModelConfig:
    selected = (profile_id or settings.llm_provider).strip().lower()
    if selected == "qwen":
        if not settings.qwen_api_key:
            raise ChatModelConfigurationError("云端 Qwen 尚未配置 QWEN_API_KEY")
        return ChatModelConfig(
            provider="openai_compatible",
            model=model_override or settings.qwen_chat_model,
            base_url=settings.qwen_base_url,
            api_key=settings.qwen_api_key,
        )
    if selected == "deepseek":
        if not settings.deepseek_api_key:
            raise ChatModelConfigurationError(
                "DeepSeek 尚未配置 DEEPSEEK_API_KEY"
            )
        return ChatModelConfig(
            provider="openai_compatible",
            model=model_override or settings.deepseek_chat_model,
            base_url=settings.deepseek_base_url,
            api_key=settings.deepseek_api_key,
            extra_body={"thinking": {"type": "disabled"}},
        )

    if profile_id is not None and selected != "ollama":
        raise ChatModelConfigurationError(f"未知的聊天模型配置：{profile_id}")
    provider = selected
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
            extra_body=config.extra_body,
        )
    raise ChatModelConfigurationError(
        "LLM_PROVIDER 仅支持 ollama、openai 或 openai_compatible"
    )
