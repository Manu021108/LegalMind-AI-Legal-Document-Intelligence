"""
Query Routes.
Handles RAG queries and system health checks.
"""

import asyncio
import logging
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional, List

from backend.services.rag_engine import query as rag_query
from backend.services.embedding_service import (
    is_ollama_available, check_model_available
)
from backend.services.llm_service import check_groq_available, check_ollama_llm_available
from backend.services.vector_store import (
    is_available as vector_store_available,
    get_collection_stats,
)
from backend.utils.rate_limit import limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Query"])


class QueryRequest(BaseModel):
    """Request body for RAG query."""
    question: str = Field(..., min_length=1, max_length=2000, description="The question to ask")
    session_id: str = Field(..., description="Session ID for conversation memory")
    doc_ids: Optional[List[str]] = Field(default=None, description="Filter to specific documents")
    mode: str = Field(default="strict", description="Response mode: 'strict' or 'hybrid'")


class QueryResponse(BaseModel):
    """Response body for RAG query."""
    answer: str
    sources: list
    provider: str
    model: str


@router.post("/query", response_model=QueryResponse)
@limiter.limit("20/minute")
async def handle_query(request: Request, query_request: QueryRequest):
    """
    Process a RAG query against uploaded legal documents.
    Rate limited to 20 requests per minute per IP.

    - **strict mode**: Answers only from document context
    - **hybrid mode**: Answers from context + general legal knowledge
    """
    if query_request.mode not in ("strict", "hybrid"):
        raise HTTPException(status_code=400, detail="Mode must be 'strict' or 'hybrid'")

    try:
        result = await rag_query(
            question=query_request.question,
            session_id=query_request.session_id,
            doc_ids=query_request.doc_ids,
            mode=query_request.mode,
        )
        return result

    except RuntimeError as e:
        logger.warning(f"Query service unavailable: {e}")
        raise HTTPException(
            status_code=503,
            detail="A required service is unavailable. Please try again shortly.",
        )
    except Exception as e:
        logger.error(f"Query failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Query processing failed. Please try again.",
        )


@router.get("/health")
async def health_check():
    """
    System health check.
    Verifies connectivity to Groq API (primary LLM), Ollama (embeddings + fallback LLM),
    and the FAISS vector store.
    """
    # Groq (primary LLM)
    groq_ok = await check_groq_available()

    # Ollama (embeddings + optional fallback LLM)
    ollama_ok = await is_ollama_available()
    embedding_model_ok = await check_model_available() if ollama_ok else False
    ollama_llm_ok = await check_ollama_llm_available() if ollama_ok else False

    # Vector store
    vs_ok = await asyncio.to_thread(vector_store_available)
    stats = await asyncio.to_thread(get_collection_stats) if vs_ok else {}

    # Embedding requires Ollama
    embedding_ready = ollama_ok and embedding_model_ok
    # LLM available via any provider
    any_llm = groq_ok or ollama_llm_ok

    # System is healthy if we have embeddings + LLM + vector store
    overall = embedding_ready and any_llm and vs_ok

    # Determine active providers
    llm_provider = "groq" if groq_ok else ("ollama" if ollama_llm_ok else "none")

    return {
        "status": "healthy" if overall else "degraded",
        "services": {
            "groq_api": {"status": "ready" if groq_ok else "unavailable", "role": "Primary LLM"},
            "ollama_server": {"status": "up" if ollama_ok else "offline"},
            "ollama_embedding": {"status": "ready" if embedding_model_ok else "not_found", "required": True},
            "ollama_llm": {"status": "ready" if ollama_llm_ok else "not_found", "optional": True},
            "vector_store": {"status": "up" if vs_ok else "down"},
        },
        "embedding_provider": "ollama" if embedding_ready else "none",
        "llm_provider": llm_provider,
        "vector_store": stats,
    }
