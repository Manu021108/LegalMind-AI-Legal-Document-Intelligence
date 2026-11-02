"""
Vector Store Service — FAISS Implementation.
Manages document embeddings using FAISS for similarity search
with JSON-based metadata storage for persistence.

Thread safety: all public operations are guarded by a re-entrant lock.
Process safety: this store is designed for a single application process
(the in-memory index is not shared between workers). Run uvicorn with a
single worker, or move to a networked vector database for multi-worker
deployments.
"""

import faiss
import numpy as np
import json
import logging
import threading
from config import VECTOR_DB_DIR

logger = logging.getLogger(__name__)

# Persistent storage paths
FAISS_INDEX_PATH = VECTOR_DB_DIR / "faiss_index.bin"
METADATA_PATH = VECTOR_DB_DIR / "metadata.json"

# In-memory state
_index = None          # FAISS index
_metadata = []         # List of metadata dicts per vector
_documents = []        # List of document texts per vector
_ids = []              # List of string IDs per vector
_dimension = None      # Embedding dimension

# Guards all reads/writes of the module-level state above
_lock = threading.RLock()


def _save_store():
    """Persist FAISS index and metadata to disk."""
    global _index
    if _index is None:
        return

    faiss.write_index(_index, str(FAISS_INDEX_PATH))
    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "ids": _ids,
            "documents": _documents,
            "metadata": _metadata,
            "dimension": _dimension,
        }, f, ensure_ascii=False)
    logger.info(f"FAISS store saved: {_index.ntotal} vectors")


def _load_store():
    """Load FAISS index and metadata from disk."""
    global _index, _metadata, _documents, _ids, _dimension

    if FAISS_INDEX_PATH.exists() and METADATA_PATH.exists():
        try:
            _index = faiss.read_index(str(FAISS_INDEX_PATH))
            with open(METADATA_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            _ids = data.get("ids", [])
            _documents = data.get("documents", [])
            _metadata = data.get("metadata", [])
            _dimension = data.get("dimension", None)
            logger.info(f"FAISS store loaded: {_index.ntotal} vectors, dim={_dimension}")
        except Exception as e:
            logger.error(f"Failed to load FAISS store: {e}")
            _init_empty()
    else:
        _init_empty()


def _init_empty():
    """Initialize empty store."""
    global _index, _metadata, _documents, _ids, _dimension
    _index = None
    _metadata = []
    _documents = []
    _ids = []
    _dimension = None


def reset_store():
    """Reset all in-memory state (primarily for tests)."""
    with _lock:
        _init_empty()


def _ensure_loaded():
    """Ensure the store is loaded."""
    global _index
    if _index is None and FAISS_INDEX_PATH.exists():
        _load_store()


def _ensure_index(dim: int):
    """Ensure FAISS index exists with the correct dimension.

    Raises:
        RuntimeError: if an existing non-empty index uses a different
            embedding dimension (e.g. the embedding model was changed).
    """
    global _index, _dimension

    if _index is not None and _index.ntotal > 0:
        if _dimension is not None and _dimension != dim:
            raise RuntimeError(
                f"Embedding dimension mismatch: the vector store holds "
                f"{_dimension}-dimensional vectors but the current embedding "
                f"model produced {dim}. Re-index the documents or remove "
                f"'{FAISS_INDEX_PATH}' and '{METADATA_PATH}'."
            )
        return

    if _index is None or _dimension != dim:
        _dimension = dim
        _index = faiss.IndexFlatIP(dim)  # Inner product (cosine on normalized vectors)
        logger.info(f"Created FAISS index with dimension {dim}")


def add_document(doc_id: str, chunks: list[dict], embeddings: list[list[float]]):
    """
    Add document chunks with embeddings to the vector store.

    Args:
        doc_id: Document identifier
        chunks: List of chunk dicts with 'text' and 'metadata'
        embeddings: Corresponding embedding vectors
    """
    if not embeddings:
        return

    with _lock:
        _ensure_loaded()

        dim = len(embeddings[0])
        _ensure_index(dim)

        # Normalize embeddings for cosine similarity via inner product
        vectors = np.array(embeddings, dtype=np.float32)
        faiss.normalize_L2(vectors)

        # Add to index
        _index.add(vectors)

        # Store metadata
        for i, chunk in enumerate(chunks):
            chunk_id = f"{doc_id}_chunk_{i}"
            _ids.append(chunk_id)
            _documents.append(chunk["text"])
            _metadata.append(chunk["metadata"])

        _save_store()
    logger.info(f"Added {len(chunks)} chunks for document '{doc_id}' to vector store")


def query(query_embedding: list[float], n_results: int = 5,
          filter_doc_ids: list[str] = None) -> list[dict]:
    """
    Query the vector store for similar chunks.

    Args:
        query_embedding: Query vector
        n_results: Number of results to return
        filter_doc_ids: Optional list of doc_ids to filter by

    Returns:
        List of result dicts with 'text', 'metadata', 'distance'
    """
    with _lock:
        _ensure_loaded()

        if _index is None or _index.ntotal == 0:
            return []

        # Normalize query vector
        query_vec = np.array([query_embedding], dtype=np.float32)
        faiss.normalize_L2(query_vec)

        # Search more than needed if filtering
        search_k = min(n_results * 3 if filter_doc_ids else n_results, _index.ntotal)

        scores, indices = _index.search(query_vec, search_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(_metadata):
                continue

            meta = _metadata[idx]

            # Apply document filter
            if filter_doc_ids and meta.get("doc_id") not in filter_doc_ids:
                continue

            results.append({
                "text": _documents[idx],
                "metadata": meta,
                "distance": float(1.0 - score),  # Convert similarity to distance
            })

            if len(results) >= n_results:
                break

        return results


def delete_document(doc_id: str):
    """
    Delete all chunks belonging to a document.

    Rebuilds the FAISS index without the deleted vectors using a single
    vector reconstruction instead of one reconstruction per kept vector.
    """
    global _index, _ids, _documents, _metadata, _dimension

    with _lock:
        _ensure_loaded()

        if _index is None or _index.ntotal == 0:
            return

        # Separate kept vs deleted entries
        keep_indices = []
        new_ids = []
        new_documents = []
        new_metadata = []
        deleted_count = 0

        for i, meta in enumerate(_metadata):
            if meta.get("doc_id") == doc_id:
                deleted_count += 1
            else:
                keep_indices.append(i)
                new_ids.append(_ids[i])
                new_documents.append(_documents[i])
                new_metadata.append(meta)

        if deleted_count == 0:
            logger.warning(f"No chunks found for document '{doc_id}' to delete")
            return

        if keep_indices:
            # Reconstruct all vectors in one call, then keep the survivors
            all_vectors = _index.reconstruct_n(0, _index.ntotal)
            kept_vectors = np.ascontiguousarray(all_vectors[keep_indices])
            _dimension = kept_vectors.shape[1]
            _index = faiss.IndexFlatIP(_dimension)
            _index.add(kept_vectors)
        else:
            _index = faiss.IndexFlatIP(_dimension) if _dimension else None

        _ids = new_ids
        _documents = new_documents
        _metadata = new_metadata

        _save_store()
    logger.info(f"Deleted {deleted_count} chunks for document '{doc_id}'")


def get_collection_stats() -> dict:
    """Get vector store statistics."""
    with _lock:
        _ensure_loaded()

        total_chunks = _index.ntotal if _index else 0

        unique_docs = set()
        for meta in _metadata:
            if meta and "doc_id" in meta:
                unique_docs.add(meta["doc_id"])

        return {
            "total_chunks": total_chunks,
            "total_documents": len(unique_docs),
            "dimension": _dimension or 0,
        }


def is_available() -> bool:
    """Check if the vector store is operational."""
    try:
        with _lock:
            _ensure_loaded()
        return True
    except Exception:
        return False
