from fastapi.testclient import TestClient

from src.api.main import app


def test_health() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_local_frontend_origins_are_allowed() -> None:
    client = TestClient(app)
    for origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
        response = client.options(
            "/api/v1/novels",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin


def test_chat_model_catalog_does_not_expose_secrets() -> None:
    response = TestClient(app).get("/api/v1/rag/chat-models")

    assert response.status_code == 200
    assert [model["id"] for model in response.json()] == [
        "ollama",
        "qwen",
        "deepseek",
    ]
    assert "api_key" not in response.text.lower()
