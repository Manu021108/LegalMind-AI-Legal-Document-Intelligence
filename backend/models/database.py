"""
SQLite database models and initialization for the Legal Document Analyzer.
Manages documents, sessions, and messages tables.
"""

import sqlite3
import json
from datetime import datetime, timedelta, timezone
import config


def get_connection() -> sqlite3.Connection:
    """Get a SQLite connection with row factory enabled."""
    conn = sqlite3.connect(str(config.SQLITE_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Initialize database tables. Safe to call multiple times (IF NOT EXISTS)."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            filepath TEXT NOT NULL,
            file_type TEXT NOT NULL,
            file_size INTEGER DEFAULT 0,
            page_count INTEGER DEFAULT 0,
            chunk_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'processing',
            upload_date TEXT NOT NULL,
            error_message TEXT
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            sources_json TEXT,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_messages_session
            ON messages(session_id, timestamp);
    """)

    conn.commit()
    conn.close()


# ── Document CRUD ──────────────────────────────────────────────────────

def insert_document(doc: dict):
    """Insert a new document record."""
    conn = get_connection()
    conn.execute(
        """INSERT INTO documents (id, name, filepath, file_type, file_size, page_count, chunk_count, status, upload_date)
           VALUES (:id, :name, :filepath, :file_type, :file_size, :page_count, :chunk_count, :status, :upload_date)""",
        doc
    )
    conn.commit()
    conn.close()


UPDATABLE_DOCUMENT_COLUMNS = {
    "name",
    "filepath",
    "file_type",
    "file_size",
    "page_count",
    "chunk_count",
    "status",
    "upload_date",
    "error_message",
}


def update_document(doc_id: str, updates: dict):
    """Update document fields by ID (columns are whitelisted)."""
    if not updates:
        return

    invalid = set(updates.keys()) - UPDATABLE_DOCUMENT_COLUMNS
    if invalid:
        raise ValueError(f"Invalid document column(s): {', '.join(sorted(invalid))}")

    conn = get_connection()
    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [doc_id]
    conn.execute(f"UPDATE documents SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()


def get_document(doc_id: str) -> dict | None:
    """Fetch a single document by ID."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_documents() -> list[dict]:
    """Fetch all documents ordered by upload date."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM documents ORDER BY upload_date DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_document_record(doc_id: str):
    """Delete a document record by ID."""
    conn = get_connection()
    conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()
    conn.close()


# ── Session CRUD ───────────────────────────────────────────────────────

def insert_session(session: dict):
    """Insert a new session."""
    conn = get_connection()
    conn.execute(
        """INSERT INTO sessions (id, title, created_at, updated_at)
           VALUES (:id, :title, :created_at, :updated_at)""",
        session
    )
    conn.commit()
    conn.close()


def get_session(session_id: str) -> dict | None:
    """Fetch a single session by ID."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_sessions() -> list[dict]:
    """Fetch all sessions with last message preview."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT s.*,
               (SELECT content FROM messages WHERE session_id = s.id ORDER BY timestamp DESC LIMIT 1) as last_message,
               (SELECT COUNT(*) FROM messages WHERE session_id = s.id) as message_count
        FROM sessions s
        ORDER BY s.updated_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_session_timestamp(session_id: str):
    """Update the updated_at timestamp for a session."""
    conn = get_connection()
    conn.execute(
        "UPDATE sessions SET updated_at = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), session_id)
    )
    conn.commit()
    conn.close()


def delete_session_record(session_id: str):
    """Delete a session and all its messages (CASCADE)."""
    conn = get_connection()
    conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()


def update_session_title(session_id: str, title: str):
    """Update the title of a session."""
    conn = get_connection()
    conn.execute(
        "UPDATE sessions SET title = ? WHERE id = ?",
        (title, session_id)
    )
    conn.commit()
    conn.close()


# ── Message CRUD ───────────────────────────────────────────────────────

def insert_message(message: dict):
    """Insert a new message."""
    conn = get_connection()
    conn.execute(
        """INSERT INTO messages (id, session_id, role, content, sources_json, timestamp)
           VALUES (:id, :session_id, :role, :content, :sources_json, :timestamp)""",
        message
    )
    conn.commit()
    conn.close()


def _messages_with_sources(rows) -> list[dict]:
    """Convert message rows into dicts and decode their sources JSON."""
    results = []
    for r in rows:
        msg = dict(r)
        if msg.get("sources_json"):
            try:
                msg["sources"] = json.loads(msg["sources_json"])
            except (TypeError, ValueError):
                msg["sources"] = []
        else:
            msg["sources"] = []
        results.append(msg)
    return results


def get_session_messages(session_id: str, limit: int = 50) -> list[dict]:
    """Fetch the first `limit` messages for a session (chronological)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp ASC LIMIT ?",
        (session_id, limit)
    ).fetchall()
    conn.close()
    return _messages_with_sources(rows)


def get_recent_messages(session_id: str, limit: int = 10) -> list[dict]:
    """Fetch the most recent `limit` messages, returned in chronological order."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM (
               SELECT * FROM messages WHERE session_id = ?
               ORDER BY timestamp DESC LIMIT ?
           ) ORDER BY timestamp ASC""",
        (session_id, limit),
    ).fetchall()
    conn.close()
    return _messages_with_sources(rows)


# ── Maintenance ────────────────────────────────────────────────────────

def get_stale_processing_documents(max_age_minutes: int = 60) -> list[dict]:
    """
    Return documents stuck in 'processing' for longer than `max_age_minutes`.

    Used at startup to clean up records left behind by a crashed/interrupted
    upload so their files do not become orphans.
    """
    cutoff = (
        datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
    ).isoformat().replace("+00:00", "Z")
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM documents WHERE status = 'processing' AND upload_date < ?",
        (cutoff,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
