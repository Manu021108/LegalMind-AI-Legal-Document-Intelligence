"""
Document Routes.
Handles document upload, listing, details, deletion, and stats.
"""

import os
import asyncio
import logging
import aiofiles
from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from typing import List

from config import (
    UPLOAD_DIR,
    ALLOWED_EXTENSIONS,
    MAX_UPLOAD_SIZE_BYTES,
    MAX_UPLOAD_SIZE_MB,
    MAX_FILES_PER_UPLOAD,
)
from backend.utils.helpers import (
    generate_id,
    get_timestamp,
    validate_file_extension,
    validate_file_content,
    is_path_within,
    safe_filename,
)
from backend.utils.rate_limit import limiter
from backend.models.database import (
    insert_document, get_document, get_all_documents,
    update_document, delete_document_record
)
from backend.services.document_processor import extract_text, chunk_text
from backend.services.embedding_service import generate_embeddings_batch
from backend.services.vector_store import (
    add_document as vs_add_document,
    delete_document as vs_delete_document,
    get_collection_stats
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["Documents"])

_CHUNK_SIZE = 1024 * 1024  # 1 MB


async def _save_upload(file: UploadFile, filepath: str) -> int:
    """
    Stream an upload to disk while enforcing the size limit.

    Returns the number of bytes written. Raises ValueError when the file
    exceeds the configured maximum size.
    """
    total = 0
    async with aiofiles.open(filepath, "wb") as buffer:
        while True:
            chunk = await file.read(_CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_UPLOAD_SIZE_BYTES:
                raise ValueError(
                    f"File exceeds the maximum size of {MAX_UPLOAD_SIZE_MB} MB."
                )
            await buffer.write(chunk)
    return total


def _remove_file(filepath: str):
    """Best-effort removal of an uploaded file."""
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
    except OSError as e:
        logger.warning(f"Could not remove file '{filepath}': {e}")


@router.post("/upload")
@limiter.limit("10/minute")
async def upload_documents(request: Request, files: List[UploadFile] = File(...)):
    """Upload and process one or more legal documents."""
    if not files:
        raise HTTPException(status_code=400, detail="No files were provided.")

    if len(files) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files. Maximum {MAX_FILES_PER_UPLOAD} files per upload.",
        )

    results = []

    for file in files:
        if not file.filename or not validate_file_extension(file.filename):
            results.append({
                "filename": file.filename or "unknown",
                "status": "error",
                "message": f"Unsupported format. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            })
            continue

        doc_id = generate_id()
        filename = safe_filename(file.filename)
        ext = os.path.splitext(filename)[1].lower()
        filepath = os.path.join(str(UPLOAD_DIR), f"{doc_id}_{filename}")
        record_inserted = False

        try:
            # Save file to disk with size enforcement
            file_size = await _save_upload(file, filepath)

            # Validate the content matches the declared extension
            is_valid, reason = await asyncio.to_thread(validate_file_content, filepath, ext)
            if not is_valid:
                _remove_file(filepath)
                results.append({
                    "filename": filename,
                    "status": "error",
                    "message": reason,
                })
                continue

            # Insert initial DB record
            doc_record = {
                "id": doc_id,
                "name": filename,
                "filepath": filepath,
                "file_type": ext,
                "file_size": file_size,
                "page_count": 0,
                "chunk_count": 0,
                "status": "processing",
                "upload_date": get_timestamp(),
            }
            await asyncio.to_thread(insert_document, doc_record)
            record_inserted = True

            # Extract text (CPU/IO bound — run off the event loop)
            extraction = await asyncio.to_thread(extract_text, filepath)
            page_count = extraction["page_count"]

            if not extraction["text"].strip():
                await asyncio.to_thread(update_document, doc_id, {
                    "status": "error",
                    "error_message": "No text could be extracted from this document."
                })
                _remove_file(filepath)
                results.append({
                    "id": doc_id,
                    "filename": filename,
                    "status": "error",
                    "message": "No text extracted"
                })
                continue

            # Chunk text
            chunks = await asyncio.to_thread(
                chunk_text,
                extraction["text"],
                doc_id,
                filename,
                extraction["pages"],
            )

            # Generate embeddings
            chunk_texts = [c["text"] for c in chunks]
            embeddings = await generate_embeddings_batch(chunk_texts)

            # Store in vector database
            await asyncio.to_thread(vs_add_document, doc_id, chunks, embeddings)

            # Update DB record
            await asyncio.to_thread(update_document, doc_id, {
                "page_count": page_count,
                "chunk_count": len(chunks),
                "status": "ready",
            })

            results.append({
                "id": doc_id,
                "filename": filename,
                "status": "ready",
                "page_count": page_count,
                "chunk_count": len(chunks),
                "message": "Document processed successfully"
            })
            logger.info(f"Document '{filename}' processed: {len(chunks)} chunks, {page_count} pages")

        except ValueError as e:
            logger.warning(f"Rejected upload '{file.filename}': {e}")
            _remove_file(filepath)
            results.append({
                "filename": file.filename or filename,
                "status": "error",
                "message": str(e),
            })
        except Exception as e:
            logger.error(f"Error processing '{file.filename}': {e}")
            if record_inserted:
                try:
                    await asyncio.to_thread(update_document, doc_id, {
                        "status": "error",
                        "error_message": "Failed to process document.",
                    })
                except Exception:
                    pass
            # Never leave an unusable upload behind on disk
            _remove_file(filepath)
            results.append({
                "id": doc_id if record_inserted else None,
                "filename": file.filename or filename,
                "status": "error",
                "message": "Failed to process document. Please try again or use a different file.",
            })

    return {"results": results}


@router.get("")
async def list_documents():
    """List all uploaded documents with metadata."""
    documents = await asyncio.to_thread(get_all_documents)
    return {"documents": documents}


@router.get("/stats")
async def document_stats():
    """Get vector store and document statistics."""
    stats = await asyncio.to_thread(get_collection_stats)
    docs = await asyncio.to_thread(get_all_documents)
    stats["total_files"] = len(docs)
    stats["ready_files"] = sum(1 for d in docs if d["status"] == "ready")
    return stats


@router.get("/{doc_id}")
async def get_document_details(doc_id: str):
    """Get details of a specific document."""
    doc = await asyncio.to_thread(get_document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.delete("/{doc_id}")
@limiter.limit("30/minute")
async def delete_document_endpoint(request: Request, doc_id: str):
    """Delete a document, its vectors, and the uploaded file."""
    doc = await asyncio.to_thread(get_document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete from vector store
    await asyncio.to_thread(vs_delete_document, doc_id)

    # Delete file from disk — only if it resolves inside UPLOAD_DIR
    filepath = doc["filepath"]
    if not is_path_within(UPLOAD_DIR, filepath):
        logger.warning(f"Refusing to delete file outside upload dir: '{filepath}'")
    else:
        _remove_file(filepath)

    # Delete from database
    await asyncio.to_thread(delete_document_record, doc_id)

    return {"message": f"Document '{doc['name']}' deleted successfully"}


@router.get("/{doc_id}/preview")
@limiter.limit("60/minute")
async def preview_document(request: Request, doc_id: str):
    """Get a text preview of a document (first 3000 characters)."""
    doc = await asyncio.to_thread(get_document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc["status"] != "ready":
        raise HTTPException(status_code=400, detail="Document is not ready for preview")

    if not is_path_within(UPLOAD_DIR, doc["filepath"]):
        logger.warning(f"Refusing to preview file outside upload dir: '{doc['filepath']}'")
        raise HTTPException(status_code=400, detail="Invalid document path")

    try:
        extraction = await asyncio.to_thread(extract_text, doc["filepath"])
        text = extraction["text"]
        preview = text[:3000]
        truncated = len(text) > 3000

        return {
            "doc_id": doc_id,
            "name": doc["name"],
            "preview": preview,
            "truncated": truncated,
            "total_length": len(text),
            "page_count": extraction["page_count"],
        }
    except Exception as e:
        logger.error(f"Failed to extract preview for '{doc_id}': {e}")
        raise HTTPException(status_code=500, detail="Failed to extract document preview")
