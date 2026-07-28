from collections.abc import Sequence

import httpx


class OllamaError(RuntimeError):
    pass


class OllamaEmbeddingClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float = 300,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def embed(
        self,
        texts: Sequence[str],
        batch_size: int = 16,
    ) -> list[list[float]]:
        vectors: list[list[float]] = []
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                for start in range(0, len(texts), batch_size):
                    response = await client.post(
                        f"{self.base_url}/api/embed",
                        json={
                            "model": self.model,
                            "input": list(texts[start : start + batch_size]),
                        },
                    )
                    response.raise_for_status()
                    result = response.json()
                    vectors.extend(result["embeddings"])
        except (httpx.HTTPError, KeyError, TypeError) as exc:
            raise OllamaError(f"Ollama Embedding 请求失败：{exc}") from exc
        if len(vectors) != len(texts):
            raise OllamaError(
                f"Ollama 返回 {len(vectors)} 个向量，预期 {len(texts)} 个"
            )
        return vectors


class OllamaChatClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float = 300,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def answer(self, system: str, prompt: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "stream": False,
                        "think": False,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt},
                        ],
                        "options": {"temperature": 0.2},
                    },
                )
                response.raise_for_status()
                content = response.json()["message"]["content"].strip()
        except (httpx.HTTPError, KeyError, TypeError) as exc:
            raise OllamaError(f"Ollama Chat 请求失败：{exc}") from exc
        if not content:
            raise OllamaError("Ollama 返回了空答案")
        if "</think>" in content:
            content = content.rsplit("</think>", 1)[-1].strip()
        if not content:
            raise OllamaError("Ollama 只返回了思维链，没有最终答案")
        return content
