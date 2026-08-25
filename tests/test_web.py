from fastapi.testclient import TestClient

from rag_platform import web
from rag_platform.config import Settings


class FakeRetrievalService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def search(self, query: str, *, top_k: int | None = None) -> tuple[list[object], float]:
        return [], 1.25


class FailingRetrievalService(FakeRetrievalService):
    def search(self, query: str, *, top_k: int | None = None) -> tuple[list[object], float]:
        raise ConnectionError("Qdrant unavailable")


def test_developer_search_home() -> None:
    client = TestClient(web.create_app(Settings()))

    response = client.get("/")
    head_response = client.head("/")

    assert response.status_code == 200
    assert "Developer Search" in response.text
    assert head_response.status_code == 200


def test_developer_search_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(web, "RetrievalService", FakeRetrievalService)
    client = TestClient(web.create_app(Settings()))

    response = client.post("/api/search", json={"query": "zero trust", "top_k": 5})

    assert response.status_code == 200
    assert response.json() == {
        "query": "zero trust",
        "latency_ms": 1.25,
        "results": [],
    }


def test_developer_search_reports_retrieval_failure(monkeypatch) -> None:
    monkeypatch.setattr(web, "RetrievalService", FailingRetrievalService)
    client = TestClient(web.create_app(Settings()))

    response = client.post("/api/search", json={"query": "zero trust"})

    assert response.status_code == 503
    assert response.json() == {"detail": "Qdrant unavailable"}
