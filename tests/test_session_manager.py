"""
Tests for Session Manager.
Validates session CRUD, message history, and auto-titling.
"""

import os
import sys
import pytest
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    """Use a temporary SQLite database for each test."""
    import config
    test_db_path = tmp_path / "test_legal.db"
    monkeypatch.setattr(config, 'SQLITE_DB_PATH', test_db_path)

    from backend.models.database import init_db
    init_db()


# ── Session CRUD Tests ─────────────────────────────────────────────────

def test_create_session():
    """Test creating a new session."""
    from backend.services.session_manager import create_session

    session = create_session("Test Session")
    assert session["id"]
    assert session["title"] == "Test Session"
    assert session["created_at"]


def test_list_sessions():
    """Test listing all sessions."""
    from backend.services.session_manager import create_session, list_all_sessions

    create_session("Session A")
    create_session("Session B")

    sessions = list_all_sessions()
    assert len(sessions) >= 2


def test_get_session_by_id():
    """Test fetching a session by ID."""
    from backend.services.session_manager import create_session, get_session_by_id

    session = create_session("Test Session")
    fetched = get_session_by_id(session["id"])
    assert fetched is not None
    assert fetched["title"] == "Test Session"


def test_delete_session():
    """Test deleting a session."""
    from backend.services.session_manager import create_session, delete_session, get_session_by_id

    session = create_session("To Delete")
    delete_session(session["id"])
    assert get_session_by_id(session["id"]) is None


# ── Message History Tests ──────────────────────────────────────────────

def test_add_and_retrieve_messages():
    """Test adding messages and retrieving history."""
    from backend.services.session_manager import create_session, add_message, get_history

    session = create_session("Chat Session")
    add_message(session["id"], "user", "What is contract law?")
    add_message(session["id"], "assistant", "Contract law governs agreements between parties.")

    history = get_history(session["id"])
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"


def test_history_limit_returns_most_recent():
    """get_history(limit=N) should return the N most recent messages in order."""
    from backend.services.session_manager import create_session, add_message, get_history

    session = create_session("Limited Session")
    for i in range(5):
        add_message(session["id"], "user", f"message {i}")

    history = get_history(session["id"], limit=3)
    assert len(history) == 3
    assert [m["content"] for m in history] == ["message 2", "message 3", "message 4"]


def test_message_with_sources():
    """Test adding messages with source citations."""
    from backend.services.session_manager import create_session, add_message, get_full_history

    session = create_session("Cited Session")
    sources = [{"doc_name": "contract.pdf", "page_number": 5, "relevance": 0.95}]
    add_message(session["id"], "assistant", "Answer text", sources=sources)

    history = get_full_history(session["id"])
    assert len(history) == 1
    assert history[0]["sources"][0]["doc_name"] == "contract.pdf"


# ── Auto-Title Tests ──────────────────────────────────────────────────

def test_auto_title_session():
    """Test auto-titling from first question."""
    from backend.services.session_manager import create_session, auto_title_session, get_session_by_id

    session = create_session("New Chat")
    auto_title_session(session["id"], "What are the key provisions of the contract?")

    updated = get_session_by_id(session["id"])
    assert updated["title"] == "What are the key provisions of the contract?"
    assert updated["title"] != "New Chat"


def test_auto_title_truncates_long_questions():
    """Test that auto-title truncates questions longer than 60 chars."""
    from backend.services.session_manager import create_session, auto_title_session, get_session_by_id

    session = create_session("New Chat")
    long_question = "What are all the legal precedents regarding intellectual property infringement in the technology sector across multiple jurisdictions?"
    auto_title_session(session["id"], long_question)

    updated = get_session_by_id(session["id"])
    assert len(updated["title"]) <= 63  # 57 + "..."
    assert updated["title"].endswith("...")


def test_auto_title_skips_named_sessions():
    """Test that auto-title doesn't overwrite custom session names."""
    from backend.services.session_manager import create_session, auto_title_session, get_session_by_id

    session = create_session("My Custom Title")
    auto_title_session(session["id"], "Some question")

    updated = get_session_by_id(session["id"])
    assert updated["title"] == "My Custom Title"
