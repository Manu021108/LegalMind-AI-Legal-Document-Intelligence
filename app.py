"""
Legal Document Analyzer — FastAPI Application Entry Point.

A RAG-based multi-document legal intelligence system.
Supports document upload, semantic search, and AI-powered Q&A
with session-based conversational memory.
"""

import os
import secrets
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from config import (
    API_AUTH_KEY,
    CORS_ORIGINS,
    UPLOAD_DIR,
    ensure_directories,
    HOST,
    PORT,
    RELOAD,
)
from backend.models.database import (
    init_db,
    get_stale_processing_documents,
    delete_document_record,
)
from backend.utils.helpers import is_path_within
from backend.utils.rate_limit import limiter
from backend.routes.document_routes import router as document_router
from backend.routes.query_routes import router as query_router
from backend.routes.session_routes import router as session_router
from backend.routes.export_routes import router as export_router

# ── Logging Configuration ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(name)-25s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Startup / Shutdown ─────────────────────────────────────────────────
def _cleanup_stale_uploads(max_age_minutes: int = 60):
    """Remove records/files left in 'processing' by an interrupted upload."""
    try:
        stale = get_stale_processing_documents(max_age_minutes=max_age_minutes)
    except Exception as e:
        logger.warning(f"Stale upload cleanup skipped: {e}")
        return

    for doc in stale:
        filepath = doc.get("filepath")
        if filepath and is_path_within(UPLOAD_DIR, filepath):
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except OSError as e:
                logger.warning(f"Could not remove stale file '{filepath}': {e}")
        try:
            delete_document_record(doc["id"])
        except Exception as e:
            logger.warning(f"Could not remove stale record '{doc['id']}': {e}")

    if stale:
        logger.info(f"Cleaned up {len(stale)} stale 'processing' document(s)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize directories/database on startup."""
    ensure_directories()
    init_db()
    _cleanup_stale_uploads()

    logger.info("=" * 60)
    logger.info("  Legal Document Analyzer — Starting Up")
    logger.info("=" * 60)
    logger.info("Database initialized")
    logger.info(f"API docs available at: http://localhost:{PORT}/docs")
    if API_AUTH_KEY:
        logger.info("API authentication: ENABLED")
    else:
        logger.info("API authentication: DISABLED (set API_AUTH_KEY in .env to enable)")
    logger.info("Deployment mode: single-process only (FAISS state is in-memory)")
    logger.info("=" * 60)
    yield


# ── FastAPI App ────────────────────────────────────────────────────────
app = FastAPI(
    title="Legal Document Analyzer",
    description="RAG-based Multi-Document Legal Intelligence System",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS Middleware ────────────────────────────────────────────────────
# Wildcard origins are incompatible with credentialed requests, so
# credentials are only enabled when explicit origins are configured.
_allow_any_origin = "*" in CORS_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _allow_any_origin else CORS_ORIGINS,
    allow_credentials=not _allow_any_origin,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key"],
)

# ── Optional API Key Authentication ───────────────────────────────────
# Set API_AUTH_KEY in .env to enable. Frontend clients may store the key
# in localStorage("apiAuthKey") and it will be sent as X-API-Key.

_PUBLIC_PATHS = {"/", "/api/health", "/openapi.json", "/favicon.ico"}
_PUBLIC_PREFIXES = ("/static", "/docs", "/redoc")


def _is_public_path(path: str) -> bool:
    """Return True if the path does not require API authentication."""
    return path in _PUBLIC_PATHS or path.startswith(_PUBLIC_PREFIXES)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Optional API key authentication middleware."""
    # Skip auth when disabled, for CORS preflight, and for public paths
    if (not API_AUTH_KEY
            or request.method == "OPTIONS"
            or _is_public_path(request.url.path)):
        return await call_next(request)

    # Constant-time comparison avoids leaking key contents via timing
    provided_key = request.headers.get("X-API-Key", "")
    if not secrets.compare_digest(provided_key, API_AUTH_KEY):
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid or missing API key. Provide X-API-Key header."},
        )

    return await call_next(request)


# ── Static Files ───────────────────────────────────────────────────────
STATIC_DIR = Path(__file__).parent / "static"
TEMPLATES_DIR = Path(__file__).parent / "templates"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ── Register API Routers ──────────────────────────────────────────────
app.include_router(document_router)
app.include_router(query_router)
app.include_router(session_router)
app.include_router(export_router)


# ── Serve Frontend SPA ────────────────────────────────────────────────
@app.get("/")
async def serve_frontend():
    """Serve the main frontend application."""
    return FileResponse(str(TEMPLATES_DIR / "index.html"))


# ── Run with Uvicorn ──────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host=HOST, port=PORT, reload=RELOAD)
