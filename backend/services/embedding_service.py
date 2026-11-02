"""
Embedding Service.
Primary: Ollama local embeddings (nomic-embed-text).
Supports single and batch embedding with retry logic.

Note: Groq API does not currently support embeddings.
Ollama is the primary embedding provider. It runs locally
and requires no API key.
"""

import httpx
import logging
import asyncio
from config import OLLAMA_BASE_URL, EMBEDDING_MODEL, EMBED_CONCURRENCY

logger = logging.getLogger(__name__)

# Timeout for embedding requests (seconds)
EMBED_TIMEOUT = 60.0
MAX_RETRIES = 3
RETRY_DELAY = 1.0


async def is_ollama_available() -> bool:
    """Check if the Ollama server is reachable."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5.0)
            return response.status_code == 200
    except Exception:
        return False


async def check_model_available(model: str = None) -> bool:
    """Check if a specific model is available in Ollama."""
    model = model or EMBEDDING_MODEL
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5.0)
            if response.status_code == 200:
                models = response.json().get("models", [])
                model_names = [m["name"].split(":")[0] for m in models]
                return model in model_names
    except Exception:
        pass
    return False


async def check_embedding_available() -> bool:
    """Check if the embedding service (Ollama) is available."""
    ollama_ok = await is_ollama_available()
    if not ollama_ok:
        return False
    return await check_model_available()


async def generate_embedding(text: str, model: str = None) -> list[float]:
    """
    Generate embedding for a single text using Ollama.

    Args:
        text: Input text to embed
        model: Model name (defaults to EMBEDDING_MODEL from config)

    Returns:
        List of floats representing the embedding vector.
    """
    model = model or EMBEDDING_MODEL

    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{OLLAMA_BASE_URL}/api/embed",
                    json={"model": model, "input": text},
                    timeout=EMBED_TIMEOUT,
                )

                # Older Ollama versions only expose the legacy endpoint
                if response.status_code == 404:
                    response = await client.post(
                        f"{OLLAMA_BASE_URL}/api/embeddings",
                        json={"model": model, "prompt": text},
                        timeout=EMBED_TIMEOUT,
                    )

                response.raise_for_status()
                data = response.json()

                # Newer API returns "embeddings" (list), legacy returns "embedding"
                if isinstance(data.get("embeddings"), list) and data["embeddings"]:
                    return data["embeddings"][0]
                if isinstance(data.get("embedding"), list):
                    return data["embedding"]
                raise RuntimeError("Ollama returned an unexpected embedding response.")

        except httpx.HTTPStatusError as e:
            logger.error(f"Ollama embedding HTTP error (attempt {attempt + 1}): {e}")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY * (2 ** attempt))
            else:
                raise RuntimeError(f"Embedding failed after {MAX_RETRIES} retries: {e}")

        except httpx.ConnectError:
            raise RuntimeError(
                "Cannot connect to Ollama for embeddings. "
                "Please start Ollama: 'ollama serve' and pull the embedding model: "
                f"'ollama pull {model}'"
            )

        except Exception as e:
            logger.error(f"Embedding error (attempt {attempt + 1}): {e}")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY * (2 ** attempt))
            else:
                raise RuntimeError(f"Embedding generation failed: {e}")


async def generate_embeddings_batch(
    texts: list[str],
    model: str = None,
    concurrency: int = None,
) -> list[list[float]]:
    """
    Generate embeddings for a batch of texts via Ollama with bounded concurrency.

    Args:
        texts: List of text strings to embed
        model: Model name (defaults to EMBEDDING_MODEL from config)
        concurrency: Max in-flight requests (defaults to EMBED_CONCURRENCY)

    Returns:
        List of embedding vectors in the same order as `texts`.
    """
    if not texts:
        return []

    concurrency = max(1, concurrency or EMBED_CONCURRENCY)
    semaphore = asyncio.Semaphore(concurrency)
    embeddings: list[list[float] | None] = [None] * len(texts)
    completed = 0
    progress_lock = asyncio.Lock()

    async def _embed(index: int, text: str):
        nonlocal completed
        async with semaphore:
            embeddings[index] = await generate_embedding(text, model)
        async with progress_lock:
            completed += 1
            if completed % 10 == 0 or completed == len(texts):
                logger.info(f"Embedded {completed}/{len(texts)} chunks")

    try:
        await asyncio.gather(*(_embed(i, text) for i, text in enumerate(texts)))
    except Exception as e:
        logger.error(f"Failed to embed batch: {e}")
        raise

    logger.info(f"Successfully embedded all {len(texts)} chunks")
    return embeddings  # type: ignore[return-value]
