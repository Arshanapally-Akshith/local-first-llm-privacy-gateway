"""Integration test: the FastAPI app boots and /health responds.

Exercises `app.main` through Starlette's TestClient rather than a
mocked route, so this goes through the same module `uvicorn app.main:app`
loads (BUILD.md Phase 0 Gate).
"""

from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_200() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
