"""
Session Manager Service.
Handles conversational memory with SQLite persistence.
"""

import json
import logging
from backend.models.database import (
    insert_session, get_session, get_all_sessions,
    update_session_timestamp, delete_session_record,
    update_session_title as db_update_title,
    insert_message, get_session_messages, get_recent_messages
)
from backend.utils.helpers import generate_id, get_timestamp
from config import MAX_HISTORY_MESSAGES

logger = logging.getLogger(__name__)


def create_session(title: str = "New Chat") -> dict:
    """Create a new conversation session."""
    now = get_timestamp()
    session = {
        "id": generate_id(),
        "title": title,
        "created_at": now,
        "updated_at": now,
    }
    insert_session(session)
    logger.info(f"Created session '{session['id']}' — {title}")
    return session


def add_message(session_id: str, role: str, content: str,
                sources: list[dict] = None) -> dict:
    """
    Add a message to a session's history.

    Args:
        session_id: Session identifier
        role: 'user' or 'assistant'
        content: Message text
        sources: Optional list of source citation dicts
    """
    message = {
        "id": generate_id(),
        "session_id": session_id,
        "role": role,
        "content": content,
        "sources_json": json.dumps(sources) if sources else None,
        "timestamp": get_timestamp(),
    }
    insert_message(message)
    update_session_timestamp(session_id)
    return message


def get_history(session_id: str, limit: int = None) -> list[dict]:
    """
    Get the most recent conversation history for building LLM context.

    Returns list of {'role': str, 'content': str} dicts in chronological order.
    """
    limit = limit or MAX_HISTORY_MESSAGES
    recent = get_recent_messages(session_id, limit=limit)
    return [{"role": m["role"], "content": m["content"]} for m in recent]


def get_full_history(session_id: str) -> list[dict]:
    """Get full message history for display."""
    return get_session_messages(session_id, limit=500)


def list_all_sessions() -> list[dict]:
    """List all sessions with metadata."""
    return get_all_sessions()


def get_session_by_id(session_id: str) -> dict | None:
    """Get session details."""
    return get_session(session_id)


def delete_session(session_id: str):
    """Delete a session and all its messages."""
    delete_session_record(session_id)
    logger.info(f"Deleted session '{session_id}'")


def auto_title_session(session_id: str, first_question: str):
    """
    Auto-generate a session title from the first user question.
    Only updates if the current title is the default 'New Chat'.
    """
    session = get_session(session_id)
    if not session or session["title"] != "New Chat":
        return

    # Truncate to ~60 chars at a word boundary
    title = first_question.strip()
    if len(title) > 60:
        title = title[:57].rsplit(' ', 1)[0] + '...'

    db_update_title(session_id, title)
    logger.info(f"Auto-titled session '{session_id}': {title}")
