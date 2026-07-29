import pytest
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from src.services.chat_models import (
    ChatModelConfig,
    ChatModelConfigurationError,
    create_chat_model,
)


def test_create_ollama_chat_model() -> None:
    model = create_chat_model(
        ChatModelConfig("ollama", "qwen3:4B", "http://ollama.test")
    )

    assert isinstance(model, ChatOllama)
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

    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "custom-model"


def test_unknown_chat_provider_is_rejected() -> None:
    with pytest.raises(ChatModelConfigurationError):
        create_chat_model(ChatModelConfig("unknown", "model"))
