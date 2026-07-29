import pytest

from src.core.config import settings
from src.services.chat_models import (
    ChatModelConfig,
    ChatModelConfigurationError,
    chat_model_options,
    create_chat_model,
    current_chat_config,
)


def test_create_ollama_chat_model() -> None:
    model = create_chat_model(
        ChatModelConfig("ollama", "qwen3:4B", "http://ollama.test")
    )

    assert model.__class__.__name__ == "ChatOllama"
    assert model.model == "qwen3:4B"
    assert model.num_ctx == 8192
    assert model.num_predict == 4096
    assert model.reasoning is True


def test_create_openai_compatible_chat_model() -> None:
    model = create_chat_model(
        ChatModelConfig(
            "openai_compatible",
            "custom-model",
            "https://example.test/v1",
            "secret",
        )
    )

    assert model.__class__.__name__ == "ChatOpenAI"
    assert model.model_name == "custom-model"


def test_unknown_chat_provider_is_rejected() -> None:
    with pytest.raises(ChatModelConfigurationError):
        create_chat_model(ChatModelConfig("unknown", "model"))


def test_chat_model_options_hide_api_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "qwen_api_key", "qwen-secret")
    monkeypatch.setattr(settings, "deepseek_api_key", "")

    options = chat_model_options()

    assert [option.id for option in options] == ["ollama", "qwen", "deepseek"]
    assert options[1].available is True
    assert options[2].available is False
    assert "qwen-secret" not in repr(options)


def test_resolve_deepseek_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "deepseek_api_key", "deepseek-secret")

    config = current_chat_config(profile_id="deepseek")

    assert config.provider == "openai_compatible"
    assert config.base_url == "https://api.deepseek.com"
    assert config.model == "deepseek-v4-flash"
    assert config.extra_body == {"thinking": {"type": "disabled"}}
