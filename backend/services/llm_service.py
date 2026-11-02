"""
LLM Service.
Primary: Groq API for high-performance inference.
Fallback: Ollama local LLM for fully offline operation.
"""

import asyncio
import time
import httpx
import logging
from groq import Groq
from config import (
    GROQ_API_KEY, LLM_MODEL,
    OLLAMA_BASE_URL, FALLBACK_LLM_MODEL,
    RAG_TEMPERATURE, RAG_MAX_TOKENS
)

logger = logging.getLogger(__name__)

# Cache Groq health results so frequent health polls do not call the API.
_GROQ_HEALTH_TTL = 60.0
_groq_health_cache: tuple[float, bool] | None = None

# ── System Prompts ─────────────────────────────────────────────────────

STRICT_SYSTEM_PROMPT = """You are an expert legal document analyst. Your role is to provide precise, well-structured answers based EXCLUSIVELY on the provided document context.

STRICT RULES:
1. Answer ONLY using information found in the provided context.
2. If the answer is not in the context, clearly state: "I cannot find this information in the provided documents."
3. ALWAYS cite your sources by mentioning the document name and page number.
4. Use precise legal terminology when present in the source documents.
5. Structure complex answers with bullet points or numbered lists for clarity.
6. If information spans multiple documents, synthesize and clearly attribute each source.
7. Never fabricate, assume, or infer information beyond what is explicitly stated."""

HYBRID_SYSTEM_PROMPT = """You are an expert legal document analyst with broad legal knowledge. Your primary role is to answer questions using the provided document context.

RULES:
1. Prioritize information from the provided document context.
2. Clearly distinguish between information FROM the documents (cite source + page) and your GENERAL legal knowledge.
3. When using general knowledge, prefix with: "[General Knowledge]"
4. When citing documents, use format: [Source: document_name, Page X]
5. Structure complex answers with bullet points or numbered lists for clarity.
6. If information spans multiple documents, synthesize and clearly attribute each source."""


def _build_messages(question: str, context: str, history: list[dict],
                    mode: str = "strict") -> list[dict]:
    """Build the message list for the LLM."""
    system_prompt = STRICT_SYSTEM_PROMPT if mode == "strict" else HYBRID_SYSTEM_PROMPT

    messages = [{"role": "system", "content": system_prompt}]

    # Add conversation history (last N turns)
    for msg in history:
        messages.append({
            "role": msg["role"],
            "content": msg["content"]
        })

    # Build the user message with context
    user_message = f"""Based on the following document excerpts, answer the question.

--- DOCUMENT CONTEXT ---
{context}
--- END CONTEXT ---

QUESTION: {question}

Provide a thorough, well-structured answer with source citations."""

    messages.append({"role": "user", "content": user_message})

    return messages


async def generate_response(question: str, context: str,
                            history: list[dict] = None,
                            mode: str = "strict") -> dict:
    """
    Generate a response using Groq API (primary) with Ollama fallback.

    Returns:
        dict with 'answer', 'provider', 'model' keys.
    """
    history = history or []
    messages = _build_messages(question, context, history, mode)

    # Try Groq first
    if GROQ_API_KEY and GROQ_API_KEY != "your_groq_api_key_here":
        try:
            result = await _generate_groq(messages)
            return result
        except Exception as e:
            logger.warning(f"Groq API failed, falling back to Ollama: {e}")

    # Fallback to Ollama
    try:
        result = await _generate_ollama(messages)
        return result
    except Exception as e:
        logger.error(f"Both Groq and Ollama failed: {e}")
        raise RuntimeError(
            "LLM generation failed. Ensure Groq API key is set or Ollama is running with a model pulled."
        )


def _generate_groq_sync(messages: list[dict]) -> dict:
    """Blocking Groq call — run in a worker thread to avoid stalling the loop."""
    client = Groq(api_key=GROQ_API_KEY)
    completion = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        temperature=RAG_TEMPERATURE,
        max_tokens=RAG_MAX_TOKENS,
    )

    answer = completion.choices[0].message.content
    logger.info(f"Groq response generated ({len(answer)} chars)")

    return {
        "answer": answer,
        "provider": "groq",
        "model": LLM_MODEL
    }


async def _generate_groq(messages: list[dict]) -> dict:
    """Generate response via Groq API without blocking the event loop."""
    try:
        return await asyncio.to_thread(_generate_groq_sync, messages)
    except Exception as e:
        logger.error(f"Groq generation error: {e}")
        raise


async def _generate_ollama(messages: list[dict]) -> dict:
    """Generate response via Ollama local LLM."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": FALLBACK_LLM_MODEL,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": RAG_TEMPERATURE,
                        "num_predict": RAG_MAX_TOKENS,
                    }
                },
                timeout=120.0,
            )
            response.raise_for_status()
            data = response.json()
            answer = data.get("message", {}).get("content", "")

            logger.info(f"Ollama response generated ({len(answer)} chars)")

            return {
                "answer": answer,
                "provider": "ollama",
                "model": FALLBACK_LLM_MODEL
            }

    except httpx.ConnectError:
        raise RuntimeError(
            "Cannot connect to Ollama. Please ensure Ollama is running: 'ollama serve'"
        )
    except Exception as e:
        logger.error(f"Ollama generation error: {e}")
        raise


def _check_groq_sync() -> bool:
    """Blocking Groq reachability check (for use in a worker thread)."""
    try:
        client = Groq(api_key=GROQ_API_KEY)
        client.models.list()
        return True
    except Exception:
        return False


async def check_groq_available(use_cache: bool = True) -> bool:
    """Check if Groq API is configured and reachable (cached briefly)."""
    global _groq_health_cache

    if not GROQ_API_KEY or GROQ_API_KEY == "your_groq_api_key_here":
        return False

    now = time.monotonic()
    if use_cache and _groq_health_cache is not None:
        cached_at, cached_value = _groq_health_cache
        if now - cached_at < _GROQ_HEALTH_TTL:
            return cached_value

    result = await asyncio.to_thread(_check_groq_sync)
    _groq_health_cache = (now, result)
    return result


async def check_ollama_llm_available() -> bool:
    """Check if Ollama has the fallback LLM model available."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5.0)
            if response.status_code == 200:
                models = response.json().get("models", [])
                model_names = [m["name"].split(":")[0] for m in models]
                return FALLBACK_LLM_MODEL in model_names
    except Exception:
        pass
    return False
