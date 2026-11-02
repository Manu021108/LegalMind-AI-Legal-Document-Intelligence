"""
Tests for Document Processor.
Validates text extraction from different file types and chunking logic.
"""

import os
import sys
import pytest
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.document_processor import extract_text, chunk_text


# ── Test Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def sample_txt_file(tmp_path):
    """Create a sample .txt file for testing."""
    content = """SUPREME COURT OF INDIA

Case No. 12345/2024
John Doe vs. State of Maharashtra

JUDGMENT

The facts of the case are as follows. The petitioner filed a writ petition
under Article 226 of the Constitution of India challenging the order dated
15th January 2024 passed by the respondent authority.

The court has examined the evidence presented by both parties and finds
that the respondent's order was passed without following due process of law.
Therefore, the impugned order is hereby set aside.

ORDER

The writ petition is allowed. The respondent shall pass a fresh order
after giving the petitioner an opportunity of being heard within 30 days.
No costs."""
    filepath = tmp_path / "test_case.txt"
    filepath.write_text(content, encoding="utf-8")
    return str(filepath)


@pytest.fixture
def empty_txt_file(tmp_path):
    """Create an empty .txt file."""
    filepath = tmp_path / "empty.txt"
    filepath.write_text("", encoding="utf-8")
    return str(filepath)


# ── Text Extraction Tests ──────────────────────────────────────────────

def test_extract_txt(sample_txt_file):
    """Test text extraction from a .txt file."""
    result = extract_text(sample_txt_file)
    assert result["text"]
    assert "SUPREME COURT" in result["text"]
    assert "John Doe" in result["text"]
    assert result["page_count"] >= 1


def test_extract_empty_txt(empty_txt_file):
    """Test extraction from an empty file returns empty text."""
    result = extract_text(empty_txt_file)
    assert result["text"].strip() == ""


def test_extract_unsupported_format(tmp_path):
    """Test extraction of unsupported format raises error."""
    filepath = tmp_path / "test.xyz"
    filepath.write_text("test content")
    with pytest.raises(ValueError, match="Unsupported"):
        extract_text(str(filepath))


# ── Chunking Tests ─────────────────────────────────────────────────────

def test_chunk_text_basic(sample_txt_file):
    """Test that text is correctly chunked with metadata."""
    extraction = extract_text(sample_txt_file)
    chunks = chunk_text(
        text=extraction["text"],
        doc_id="test-doc-001",
        doc_name="test_case.txt",
        pages=extraction["pages"],
    )

    assert len(chunks) >= 1
    for chunk in chunks:
        assert "text" in chunk
        assert "metadata" in chunk
        assert chunk["metadata"]["doc_id"] == "test-doc-001"
        assert chunk["metadata"]["doc_name"] == "test_case.txt"
        assert chunk["text"].strip()  # No empty chunks


def test_chunk_text_empty():
    """Test chunking empty text returns empty list."""
    chunks = chunk_text(
        text="",
        doc_id="test-doc-002",
        doc_name="empty.txt",
        pages=[],
    )
    assert chunks == []


def test_chunk_metadata_has_required_fields(sample_txt_file):
    """Test that chunk metadata contains all required fields."""
    extraction = extract_text(sample_txt_file)
    chunks = chunk_text(
        text=extraction["text"],
        doc_id="test-doc-003",
        doc_name="test_case.txt",
        pages=extraction["pages"],
    )

    required_fields = {"doc_id", "doc_name", "chunk_index"}
    for chunk in chunks:
        metadata = chunk["metadata"]
        assert required_fields.issubset(metadata.keys()), f"Missing metadata fields: {required_fields - metadata.keys()}"
