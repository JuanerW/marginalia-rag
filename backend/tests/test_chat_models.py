import pytest

from src.services.chat_models import (
    ChatModelConfig,
    ChatModelConfigurationError,
    create_chat_model,
)


def test_create_ollama_chat_model() -> None:
    model = create_chat_model(
        ChatModelConfig("ollama", "qwen3:4B", "http://ollama.test")
    )

    assert model.__class__.__name__ == "ChatOllama"
    assert model.model == "qwen3:4B"


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
