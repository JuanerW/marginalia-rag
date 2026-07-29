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
