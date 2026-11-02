"""
Tests for security hardening and regression fixes.
Covers auth middleware, upload validation/limits, export, error sanitizing,
provider fallback, and helper behavior.
"""

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app
import app as app_module
import backend.routes.document_routes as document_routes
import backend.services.llm_service as llm
from backend.models.database import init_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    """Use a temporary SQLite database for each test."""
    import config
    monkeypatch.setattr(config, "SQLITE_DB_PATH", tmp_path / "test_security.db")
    init_db()
    yield


# ── Auth middleware ────────────────────────────────────────────────────

def test_auth_requires_key(monkeypatch):
    monkeypatch.setattr(app_module, "API_AUTH_KEY", "secret-key")

    response = client.post("/api/sessions", json={"title": "No Key"})
    assert response.status_code == 401

    response = client.post(
        "/api/sessions",
        json={"title": "With Key"},
        headers={"X-API-Key": "secret-key"},
    )
    assert response.status_code == 200


def test_auth_allows_public_paths(monkeypatch):
    monkeypatch.setattr(app_module, "API_AUTH_KEY", "secret-key")
    response = client.get("/api/health")
    assert response.status_code == 200


def test_auth_allows_preflight(monkeypatch):
    monkeypatch.setattr(app_module, "API_AUTH_KEY", "secret-key")
    response = client.options(
        "/api/sessions",
        headers={
            "Origin": "http://localhost:8000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code in (200, 204)


# ── Upload validation / limits ────────────────────────────────────────

def _upload_dir(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(document_routes, "UPLOAD_DIR", upload_dir)
    return upload_dir


def test_upload_rejects_binary_txt(tmp_path, monkeypatch):
    upload_dir = _upload_dir(tmp_path, monkeypatch)

    response = client.post(
        "/api/documents/upload",
        files={"files": ("fake.txt", b"\x00\x01\x02binary", "text/plain")},
    )
    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["status"] == "error"
    assert not list(upload_dir.iterdir())


def test_upload_rejects_fake_pdf(tmp_path, monkeypatch):
    upload_dir = _upload_dir(tmp_path, monkeypatch)

    response = client.post(
        "/api/documents/upload",
        files={"files": ("fake.pdf", b"this is not a pdf", "application/pdf")},
    )
    result = response.json()["results"][0]
    assert result["status"] == "error"
    assert "PDF" in result["message"]
    assert not list(upload_dir.iterdir())


def test_upload_enforces_size_limit(tmp_path, monkeypatch):
    upload_dir = _upload_dir(tmp_path, monkeypatch)
    monkeypatch.setattr(document_routes, "MAX_UPLOAD_SIZE_BYTES", 8)
    monkeypatch.setattr(document_routes, "MAX_UPLOAD_SIZE_MB", 1)

    response = client.post(
        "/api/documents/upload",
        files={"files": ("big.txt", b"x" * 64, "text/plain")},
    )
    result = response.json()["results"][0]
    assert result["status"] == "error"
    assert "maximum size" in result["message"].lower()
    assert not list(upload_dir.iterdir())


def test_upload_enforces_file_count(monkeypatch):
    monkeypatch.setattr(document_routes, "MAX_FILES_PER_UPLOAD", 1)

    response = client.post(
        "/api/documents/upload",
        files=[
            ("files", ("a.txt", b"hello", "text/plain")),
            ("files", ("b.txt", b"world", "text/plain")),
        ],
    )
    assert response.status_code == 400


# ── Export ────────────────────────────────────────────────────────────

def test_export_contains_messages():
    from backend.services.session_manager import create_session, add_message

    session = create_session("Export Test")
    add_message(session["id"], "user", "What is the term?")
    add_message(session["id"], "assistant", "The term is twelve months.")

    response = client.get(f"/api/sessions/{session['id']}/export")
    assert response.status_code == 200
    assert "What is the term?" in response.text
    assert "twelve months" in response.text
    assert "attachment" in response.headers["content-disposition"]


# ── Error sanitizing ──────────────────────────────────────────────────

def test_query_runtime_error_is_sanitized(monkeypatch):
    import backend.routes.query_routes as query_routes

    async def _boom(**kwargs):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(query_routes, "rag_query", _boom)
    response = client.post("/api/query", json={
        "question": "test",
        "session_id": "any",
        "mode": "strict",
    })
    assert response.status_code == 503
    assert "secret internal detail" not in response.json()["detail"]


# ── Provider fallback ─────────────────────────────────────────────────

def test_llm_falls_back_to_ollama(monkeypatch):
    async def _groq_fails(messages):
        raise RuntimeError("groq down")

    async def _ollama_ok(messages):
        return {"answer": "hi", "provider": "ollama", "model": "llama3.2"}

    monkeypatch.setattr(llm, "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(llm, "_generate_groq", _groq_fails)
    monkeypatch.setattr(llm, "_generate_ollama", _ollama_ok)

    result = asyncio.run(llm.generate_response("question", "context"))
    assert result["provider"] == "ollama"


# ── Helpers ───────────────────────────────────────────────────────────

def test_timestamp_is_timezone_aware():
    from backend.utils.helpers import get_timestamp

    timestamp = get_timestamp()
    assert timestamp.endswith("Z") or "+" in timestamp


def test_safe_filename_strips_traversal():
    from backend.utils.helpers import safe_filename

    assert safe_filename("../../etc/passwd") == "passwd"
    assert ".." not in safe_filename("..\\..\\evil.txt")


def test_is_path_within(tmp_path):
    from backend.utils.helpers import is_path_within

    inside = tmp_path / "file.txt"
    outside = tmp_path.parent / "outside.txt"
    assert is_path_within(tmp_path, inside)
    assert not is_path_within(tmp_path, outside)
