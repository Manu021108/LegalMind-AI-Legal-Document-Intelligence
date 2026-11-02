"""
Tests for API Routes.
Uses FastAPI TestClient to verify endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import os
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app
from backend.models.database import init_db

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    """Use a temporary SQLite database for each test."""
    import config
    test_db_path = tmp_path / "test_api_legal.db"
    monkeypatch.setattr(config, 'SQLITE_DB_PATH', test_db_path)
    init_db()

# ── Health Check Tests ────────────────────────────────────────────────

def test_health_check(monkeypatch):
    """Test the health check endpoint without calling live providers."""
    import backend.routes.query_routes as query_routes

    async def _ready():
        return True

    async def _embedding_model_ready():
        return True

    monkeypatch.setattr(query_routes, "check_groq_available", _ready)
    monkeypatch.setattr(query_routes, "is_ollama_available", _ready)
    monkeypatch.setattr(query_routes, "check_model_available", _embedding_model_ready)
    monkeypatch.setattr(query_routes, "check_ollama_llm_available", _ready)
    monkeypatch.setattr(query_routes, "vector_store_available", lambda: True)
    monkeypatch.setattr(query_routes, "get_collection_stats", lambda: {
        "total_chunks": 0, "total_documents": 0, "dimension": 0
    })

    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "services" in data
    assert "vector_store" in data

# ── Session Routes Tests ──────────────────────────────────────────────

def test_create_session_api():
    """Test creating a session via API."""
    response = client.post("/api/sessions", json={"title": "API Test Session"})
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert data["title"] == "API Test Session"

def test_list_sessions_api():
    """Test listing sessions via API."""
    client.post("/api/sessions", json={"title": "Session 1"})
    client.post("/api/sessions", json={"title": "Session 2"})
    
    response = client.get("/api/sessions")
    assert response.status_code == 200
    data = response.json()
    assert len(data["sessions"]) >= 2

def test_get_session_api():
    """Test getting a specific session."""
    create_resp = client.post("/api/sessions", json={"title": "Single Session"})
    session_id = create_resp.json()["id"]
    
    response = client.get(f"/api/sessions/{session_id}")
    assert response.status_code == 200
    assert response.json()["title"] == "Single Session"

# ── Document Routes Tests ─────────────────────────────────────────────

def test_list_documents_api():
    """Test listing documents (empty)."""
    response = client.get("/api/documents")
    assert response.status_code == 200
    assert "documents" in response.json()

def test_get_doc_stats_api():
    """Test document statistics."""
    response = client.get("/api/documents/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_files" in data
    assert "total_chunks" in data

# ── Query Route Tests ─────────────────────────────────────────────────

def test_query_invalid_mode():
    """Test query with invalid mode."""
    response = client.post("/api/query", json={
        "question": "test",
        "session_id": "test-session",
        "mode": "invalid"
    })
    assert response.status_code == 400
    assert "Mode must be 'strict' or 'hybrid'" in response.json()["detail"]

# ── Export Route Tests ────────────────────────────────────────────────

def test_export_nonexistent_session():
    """Test exporting a non-existent session."""
    response = client.get("/api/sessions/nonexistent/export")
    assert response.status_code == 404
