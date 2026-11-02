"""
Batch Import Script.
Import multiple .txt / .pdf / .docx files from a directory into the Legal Document Analyzer.

Usage:
    python batch_import.py ./path/to/documents/

This processes documents through the same pipeline as the web UI:
  1. Copy file to uploads/
  2. Extract text
  3. Chunk text
  4. Generate embeddings (via Groq or Ollama)
  5. Store in FAISS vector database
  6. Record in SQLite
"""

import os
import sys
import shutil
import asyncio
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config import UPLOAD_DIR, ALLOWED_EXTENSIONS, ensure_directories
from backend.utils.helpers import generate_id, get_timestamp, safe_filename
from backend.models.database import init_db, insert_document, update_document
from backend.services.document_processor import extract_text, chunk_text
from backend.services.embedding_service import generate_embeddings_batch
from backend.services.vector_store import add_document as vs_add_document

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


async def import_file(filepath: str, index: int, total: int) -> dict:
    """Import a single file through the full pipeline."""
    filename = os.path.basename(filepath)
    ext = os.path.splitext(filename)[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        logger.warning(f"  [{index}/{total}] Skipping '{filename}' — unsupported format")
        return {"filename": filename, "status": "skipped", "reason": "unsupported format"}

    doc_id = generate_id()
    safe_name = safe_filename(filename)
    dest_path = os.path.join(str(UPLOAD_DIR), f"{doc_id}_{safe_name}")

    try:
        # Copy file
        shutil.copy2(filepath, dest_path)
        file_size = os.path.getsize(dest_path)

        # Insert DB record
        doc_record = {
            "id": doc_id,
            "name": safe_name,
            "filepath": dest_path,
            "file_type": ext,
            "file_size": file_size,
            "page_count": 0,
            "chunk_count": 0,
            "status": "processing",
            "upload_date": get_timestamp(),
        }
        insert_document(doc_record)

        # Extract text
        extraction = extract_text(dest_path)
        if not extraction["text"].strip():
            update_document(doc_id, {"status": "error", "error_message": "No text extracted"})
            logger.warning(f"  [{index}/{total}] '{filename}' — no text extracted")
            return {"filename": filename, "status": "error", "reason": "no text extracted"}

        # Chunk
        chunks = chunk_text(
            text=extraction["text"],
            doc_id=doc_id,
            doc_name=safe_name,
            pages=extraction["pages"],
        )

        # Embed
        chunk_texts = [c["text"] for c in chunks]
        embeddings = await generate_embeddings_batch(chunk_texts)

        # Store in vector DB
        vs_add_document(doc_id, chunks, embeddings)

        # Update DB
        update_document(doc_id, {
            "page_count": extraction["page_count"],
            "chunk_count": len(chunks),
            "status": "ready",
        })

        logger.info(f"  [{index}/{total}] ✓ '{filename}' — {len(chunks)} chunks, {extraction['page_count']} pages")
        return {"filename": filename, "status": "ready", "chunks": len(chunks)}

    except Exception as e:
        logger.error(f"  [{index}/{total}] ✗ '{filename}' — {e}")
        try:
            update_document(doc_id, {"status": "error", "error_message": str(e)})
        except Exception:
            pass
        return {"filename": filename, "status": "error", "reason": str(e)}


async def main():
    if len(sys.argv) < 2:
        print("Usage: python batch_import.py <directory_path>")
        print("Example: python batch_import.py ./case_docs/")
        sys.exit(1)

    source_dir = Path(sys.argv[1])
    if not source_dir.is_dir():
        print(f"Error: '{source_dir}' is not a valid directory")
        sys.exit(1)

    # Initialize directories and database
    ensure_directories()
    init_db()

    # Collect files
    files = []
    for ext in ALLOWED_EXTENSIONS:
        files.extend(source_dir.glob(f"*{ext}"))
    files.sort()

    if not files:
        print(f"No supported files found in '{source_dir}'")
        print(f"Supported formats: {', '.join(ALLOWED_EXTENSIONS)}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  Legal Document Analyzer — Batch Document Import")
    print(f"{'='*60}")
    print(f"  Source: {source_dir.resolve()}")
    print(f"  Files found: {len(files)}")
    print(f"{'='*60}\n")

    results = {"ready": 0, "error": 0, "skipped": 0}

    for i, filepath in enumerate(files, 1):
        result = await import_file(str(filepath), i, len(files))
        results[result["status"]] = results.get(result["status"], 0) + 1

    print(f"\n{'='*60}")
    print(f"  Import Complete")
    print(f"{'='*60}")
    print(f"  ✓ Successfully imported: {results['ready']}")
    print(f"  ✗ Errors: {results['error']}")
    print(f"  ⊘ Skipped: {results['skipped']}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
