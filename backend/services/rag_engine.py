"""
RAG Engine.
Orchestrates the full Retrieval-Augmented Generation pipeline:
  1. Embed query
  2. Retrieve relevant chunks from vector store
  3. Build context with conversation history
  4. Generate LLM response with source citations
"""

import asyncio
import logging
from backend.services.embedding_service import generate_embedding
from backend.services.vector_store import query as vector_query
from backend.services.llm_service import generate_response
from backend.services.session_manager import get_history, add_message, auto_title_session
from config import RAG_TOP_K

logger = logging.getLogger(__name__)


async def query(question: str, session_id: str,
                doc_ids: list[str] = None,
                mode: str = "strict") -> dict:
    """
    Execute a full RAG query.

    Args:
        question: User's natural language question
        session_id: Current session ID for memory
        doc_ids: Optional filter to specific documents
        mode: 'strict' (context-only) or 'hybrid' (context + knowledge)

    Returns:
        dict with 'answer', 'sources', 'provider', 'model'
    """
    logger.info(f"RAG query: '{question[:80]}...' | mode={mode} | docs={doc_ids}")

    # Step 1: Embed the query
    try:
        query_embedding = await generate_embedding(question)
    except Exception as e:
        logger.error(f"Failed to embed query: {e}")
        raise RuntimeError(f"Embedding service error: {e}")

    # Step 2: Retrieve relevant chunks (FAISS is synchronous)
    retrieved = await asyncio.to_thread(
        vector_query,
        query_embedding=query_embedding,
        n_results=RAG_TOP_K,
        filter_doc_ids=doc_ids,
    )

    if not retrieved:
        # No documents found — return helpful message
        no_docs_msg = ("No relevant information was found in the uploaded documents. "
                       "Please ensure you have uploaded the relevant documents and try rephrasing your question.")
        await asyncio.to_thread(add_message, session_id, "user", question)
        await asyncio.to_thread(add_message, session_id, "assistant", no_docs_msg)
        await asyncio.to_thread(auto_title_session, session_id, question)
        return {
            "answer": no_docs_msg,
            "sources": [],
            "provider": "system",
            "model": "none",
        }

    # Step 3: Build context from retrieved chunks
    context = _build_context(retrieved)
    sources = _extract_sources(retrieved)

    # Step 4: Get conversation history
    history = await asyncio.to_thread(get_history, session_id)

    # Step 5: Generate LLM response
    try:
        llm_result = await generate_response(
            question=question,
            context=context,
            history=history,
            mode=mode,
        )
    except Exception as e:
        logger.error(f"LLM generation failed: {e}")
        raise RuntimeError(f"LLM service error: {e}")

    # Step 6: Save to session history
    await asyncio.to_thread(add_message, session_id, "user", question)
    await asyncio.to_thread(
        add_message, session_id, "assistant", llm_result["answer"], sources
    )

    # Step 7: Auto-title the session from the first question
    await asyncio.to_thread(auto_title_session, session_id, question)

    return {
        "answer": llm_result["answer"],
        "sources": sources,
        "provider": llm_result["provider"],
        "model": llm_result["model"],
    }


def _build_context(retrieved_chunks: list[dict]) -> str:
    """Format retrieved chunks into a context string for the LLM."""
    context_parts = []

    for i, chunk in enumerate(retrieved_chunks, 1):
        meta = chunk["metadata"]
        doc_name = meta.get("doc_name", "Unknown")
        page = meta.get("page_number", "?")
        similarity = 1 - chunk.get("distance", 0)  # Convert distance to similarity

        header = f"[Excerpt {i} | Source: {doc_name} | Page: {page} | Relevance: {similarity:.1%}]"
        context_parts.append(f"{header}\n{chunk['text']}")

    return "\n\n---\n\n".join(context_parts)


def _extract_sources(retrieved_chunks: list[dict]) -> list[dict]:
    """Extract deduplicated source citations from retrieved chunks."""
    seen = set()
    sources = []

    for chunk in retrieved_chunks:
        meta = chunk["metadata"]
        key = (meta.get("doc_id"), meta.get("page_number"))

        if key not in seen:
            seen.add(key)
            sources.append({
                "doc_id": meta.get("doc_id", ""),
                "doc_name": meta.get("doc_name", "Unknown"),
                "page_number": meta.get("page_number", 1),
                "chunk_index": meta.get("chunk_index", 0),
                "relevance": round(1 - chunk.get("distance", 0), 3),
            })

    # Sort by relevance descending
    sources.sort(key=lambda x: x["relevance"], reverse=True)
    return sources
