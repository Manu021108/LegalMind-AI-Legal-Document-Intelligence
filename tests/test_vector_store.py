"""
Tests for Vector Store (FAISS).
Validates add, query, delete cycle and persistence logic.
"""

import os
import sys
import json
import numpy as np
import pytest
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def reset_vector_store(tmp_path, monkeypatch):
    """Reset the vector store for each test with a temporary directory."""
    import backend.services.vector_store as vs

    monkeypatch.setattr(vs, 'FAISS_INDEX_PATH', tmp_path / "faiss_index.bin")
    monkeypatch.setattr(vs, 'METADATA_PATH', tmp_path / "metadata.json")
    vs.reset_store()
    yield
    vs.reset_store()


def _make_chunks(doc_id, doc_name, count=3, dim=8):
    """Helper: generate fake chunks with embeddings."""
    chunks = []
    embeddings = []
    for i in range(count):
        chunks.append({
            "text": f"Chunk {i} of {doc_name}",
            "metadata": {
                "doc_id": doc_id,
                "doc_name": doc_name,
                "chunk_index": i,
                "page_number": 1,
            }
        })
        vec = np.random.randn(dim).astype(np.float32)
        vec = vec / np.linalg.norm(vec)  # Normalize for inner product
        embeddings.append(vec.tolist())
    return chunks, embeddings


# ── Add & Query Tests ──────────────────────────────────────────────────

def test_add_document():
    """Test adding a document to the vector store."""
    from backend.services.vector_store import add_document, get_collection_stats

    chunks, embeddings = _make_chunks("doc-001", "case_law.txt", count=5, dim=8)
    add_document("doc-001", chunks, embeddings)

    stats = get_collection_stats()
    assert stats["total_chunks"] == 5


def test_query_returns_results():
    """Test querying returns relevant chunks."""
    from backend.services.vector_store import add_document, query

    chunks, embeddings = _make_chunks("doc-001", "case_law.txt", count=5, dim=8)
    add_document("doc-001", chunks, embeddings)

    # Query with one of the embeddings (should match itself)
    results = query(query_embedding=embeddings[0], n_results=3)
    assert len(results) > 0
    assert len(results) <= 3
    assert "text" in results[0]
    assert "metadata" in results[0]


def test_query_with_filter():
    """Test querying with document filter."""
    from backend.services.vector_store import add_document, query

    chunks1, emb1 = _make_chunks("doc-001", "case_a.txt", count=3, dim=8)
    chunks2, emb2 = _make_chunks("doc-002", "case_b.txt", count=3, dim=8)
    add_document("doc-001", chunks1, emb1)
    add_document("doc-002", chunks2, emb2)

    results = query(query_embedding=emb1[0], n_results=10, filter_doc_ids=["doc-001"])
    assert all(r["metadata"]["doc_id"] == "doc-001" for r in results)


# ── Delete Tests ───────────────────────────────────────────────────────

def test_delete_document():
    """Test deleting a document removes its chunks."""
    from backend.services.vector_store import add_document, delete_document, get_collection_stats

    chunks1, emb1 = _make_chunks("doc-001", "case_a.txt", count=3, dim=8)
    chunks2, emb2 = _make_chunks("doc-002", "case_b.txt", count=4, dim=8)
    add_document("doc-001", chunks1, emb1)
    add_document("doc-002", chunks2, emb2)

    assert get_collection_stats()["total_chunks"] == 7

    delete_document("doc-001")
    stats = get_collection_stats()
    assert stats["total_chunks"] == 4


def test_delete_nonexistent_document():
    """Test deleting a non-existent document doesn't crash."""
    from backend.services.vector_store import add_document, delete_document, get_collection_stats

    chunks, emb = _make_chunks("doc-001", "case.txt", count=3, dim=8)
    add_document("doc-001", chunks, emb)

    delete_document("doc-nonexistent")
    assert get_collection_stats()["total_chunks"] == 3


def test_delete_all_documents():
    """Test deleting all documents leaves an empty store."""
    from backend.services.vector_store import add_document, delete_document, get_collection_stats

    chunks, emb = _make_chunks("doc-001", "case.txt", count=3, dim=8)
    add_document("doc-001", chunks, emb)
    delete_document("doc-001")

    stats = get_collection_stats()
    assert stats["total_chunks"] == 0


# ── Persistence Tests ──────────────────────────────────────────────────

def test_dimension_mismatch_raises():
    """Adding chunks with a different embedding dimension must fail loudly."""
    from backend.services.vector_store import add_document

    chunks1, emb1 = _make_chunks("doc-001", "case_a.txt", count=2, dim=8)
    add_document("doc-001", chunks1, emb1)

    chunks2, emb2 = _make_chunks("doc-002", "case_b.txt", count=2, dim=16)
    with pytest.raises(RuntimeError):
        add_document("doc-002", chunks2, emb2)


def test_persistence(tmp_path):
    """Test that data persists after save and reload."""
    from backend.services.vector_store import add_document, get_collection_stats
    import backend.services.vector_store as vs

    chunks, emb = _make_chunks("doc-001", "case.txt", count=3, dim=8)
    add_document("doc-001", chunks, emb)
    assert get_collection_stats()["total_chunks"] == 3

    # Simulate reload by resetting in-memory state
    vs._index = None
    vs._ids = []
    vs._documents = []
    vs._metadata = []

    stats = get_collection_stats()
    assert stats["total_chunks"] == 3
