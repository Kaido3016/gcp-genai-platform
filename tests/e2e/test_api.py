"""End-to-end tests exercising the FastAPI app through its HTTP interface,
using the local mock AI backend and in-memory/local storage (no GCP
credentials or network required)."""

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("GCP_USE_LIVE_VERTEX_AI", "false")


@pytest.fixture
def client(monkeypatch, tmp_path):
    # Import app fresh per test module run; dependencies use lru_cache
    # singletons so we reset them to avoid state leaking across tests.
    from app import dependencies
    from app.main import app

    dependencies.reset_caches_for_tests()
    monkeypatch.setenv("GCP_USE_LIVE_VERTEX_AI", "false")
    with TestClient(app) as c:
        yield c
    dependencies.reset_caches_for_tests()


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["live_vertex_ai"] is False


def test_readyz(client):
    response = client.get("/readyz")
    assert response.status_code == 200


def test_upload_document_success(client):
    files = {"file": ("notes.txt", b"Cloud Run scales to zero when idle.", "text/plain")}
    response = client.post("/documents/upload", files=files)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "indexed"
    assert body["filename"] == "notes.txt"
    assert "document_id" in body


def test_upload_document_rejects_bad_extension(client):
    files = {"file": ("virus.exe", b"MZ", "application/octet-stream")}
    response = client.post("/documents/upload", files=files)
    assert response.status_code == 422


def test_get_document_status_after_upload(client):
    files = {"file": ("a.txt", b"Some content about pricing tiers.", "text/plain")}
    upload_resp = client.post("/documents/upload", files=files)
    document_id = upload_resp.json()["document_id"]

    status_resp = client.get(f"/documents/{document_id}")
    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["metadata"]["document_id"] == document_id
    assert body["metadata"]["status"] == "indexed"


def test_get_document_status_404_for_unknown_id(client):
    response = client.get("/documents/does-not-exist")
    assert response.status_code == 404


def test_chat_returns_grounded_answer_with_citations(client):
    files = {
        "file": (
            "guide.txt",
            b"Vertex AI Vector Search supports approximate nearest neighbor queries.",
            "text/plain",
        )
    }
    client.post("/documents/upload", files=files)

    response = client.post("/chat", json={"query": "What does Vertex AI Vector Search support?"})
    assert response.status_code == 200
    body = response.json()
    assert "answer" in body
    assert isinstance(body["citations"], list)
    assert body["grounded"] is True
    assert len(body["citations"]) >= 1
    assert body["citations"][0]["filename"] == "guide.txt"


def test_chat_ungrounded_when_no_documents(client):
    response = client.post("/chat", json={"query": "Anything at all?"})
    assert response.status_code == 200
    body = response.json()
    assert body["grounded"] is False
    assert body["citations"] == []


def test_chat_rejects_blank_query(client):
    response = client.post("/chat", json={"query": "   "})
    assert response.status_code == 422


def test_agent_endpoint_executes_calculator(client):
    response = client.post("/agent", json={"query": "What is 6 + 6?"})
    assert response.status_code == 200
    body = response.json()
    assert body["stopped_reason"] in ("final_answer", "max_iterations")
    tool_names = [s["tool_call"]["tool"] for s in body["steps"] if s.get("tool_call")]
    assert "calculator" in tool_names


def test_agent_endpoint_rejects_empty_query(client):
    response = client.post("/agent", json={"query": ""})
    assert response.status_code == 422


def test_request_id_header_echoed(client):
    response = client.get("/healthz", headers={"X-Request-ID": "test-correlation-123"})
    assert response.headers.get("X-Request-ID") == "test-correlation-123"
