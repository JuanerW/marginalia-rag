import httpx
import pytest

from src.services.ollama import (
    OllamaChatClient,
    OllamaEmbeddingClient,
    OllamaError,
)


@pytest.mark.asyncio
async def test_ollama_embedding_client_batches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        inputs = __import__("json").loads(request.content)["input"]
        requests.append(inputs)
        return httpx.Response(
            200,
            json={"embeddings": [[float(len(text)), 1.0] for text in inputs]},
        )

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient

    def client_factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    client = OllamaEmbeddingClient("http://ollama.test", "bge-m3")

    vectors = await client.embed(["一", "二二", "三三三"], batch_size=2)

    assert vectors == [[1.0, 1.0], [2.0, 1.0], [3.0, 1.0]]
    assert requests == [["一", "二二"], ["三三三"]]


@pytest.mark.asyncio
async def test_ollama_embedding_client_wraps_http_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(500, request=request)
    )
    original_client = httpx.AsyncClient

    def client_factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)

    with pytest.raises(OllamaError):
        await OllamaEmbeddingClient(
            "http://ollama.test",
            "missing",
        ).embed(["测试"])


@pytest.mark.asyncio
async def test_ollama_chat_client_returns_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        assert payload["think"] is False
        assert payload["messages"][0]["role"] == "system"
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": "<think>内部推理不应展示</think>\n刘慈欣。[1]"
                }
            },
        )

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient

    def client_factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    answer = await OllamaChatClient(
        "http://ollama.test",
        "qwen3:4B",
    ).answer("只按证据回答", "作者是谁？")

    assert answer == "刘慈欣。[1]"
