"""
Centralized configuration for the Legal Document Analyzer.
Loads settings from .env file and provides defaults.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Base Paths ──────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / os.getenv("UPLOAD_DIR", "uploads")
VECTOR_DB_DIR = BASE_DIR / os.getenv("VECTOR_DB_DIR", "vector_db")
SQLITE_DB_PATH = BASE_DIR / os.getenv("SQLITE_DB_PATH", "data/legal_docs.db")

# ── Ollama (Embeddings + Fallback LLM) ─────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
FALLBACK_LLM_MODEL = os.getenv("FALLBACK_LLM_MODEL", "llama3.2")
EMBED_CONCURRENCY = int(os.getenv("EMBED_CONCURRENCY", "4"))

# ── Server ─────────────────────────────────────────────────────────────
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
RELOAD = os.getenv("RELOAD", "false").lower() in {"1", "true", "yes"}

# ── Groq API (Primary LLM) ─────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.1-70b-versatile")

# ── Chunking Parameters ────────────────────────────────────────────────
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
CHUNK_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]

# ── RAG Parameters ─────────────────────────────────────────────────────
RAG_TOP_K = 5
RAG_TEMPERATURE = 0.1
RAG_MAX_TOKENS = 2048

# ── Session / Memory ───────────────────────────────────────────────────
MAX_HISTORY_MESSAGES = 10

# ── Allowed File Extensions ────────────────────────────────────────────
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}

# ── Upload Limits ──────────────────────────────────────────────────────
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50"))
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024
MAX_FILES_PER_UPLOAD = int(os.getenv("MAX_FILES_PER_UPLOAD", "10"))

# ── Security ───────────────────────────────────────────────────────────
# Leave empty to disable API-key authentication (recommended only for local dev).
API_AUTH_KEY = os.getenv("API_AUTH_KEY", "")

# Comma-separated list of allowed CORS origins. Defaults to localhost only.
# Use "*" to allow any origin (credentials will be disabled automatically).
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:8000,http://127.0.0.1:8000",
    ).split(",")
    if origin.strip()
]

# ── Directory Helpers ──────────────────────────────────────────────────
def ensure_directories():
    """Create the runtime data directories if they do not exist.

    Kept as an explicit call (startup / batch import) instead of running at
    import time so importing config has no filesystem side effects.
    """
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True)
    SQLITE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
