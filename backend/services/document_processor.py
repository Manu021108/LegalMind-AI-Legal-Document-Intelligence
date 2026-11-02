"""
Document Processor Service.
Handles extraction of text from PDF, DOCX, and TXT files,
and semantic chunking with metadata enrichment.
"""

import fitz  # PyMuPDF
from docx import Document as DocxDocument
from docx.oxml.ns import qn
from langchain_text_splitters import RecursiveCharacterTextSplitter
from config import CHUNK_SIZE, CHUNK_OVERLAP, CHUNK_SEPARATORS
from backend.utils.helpers import get_file_extension


def extract_text(filepath: str) -> dict:
    """
    Extract text from a document file.

    Returns:
        dict with keys:
            - 'text': full extracted text
            - 'pages': list of {page_number, content} dicts
            - 'page_count': total pages
    """
    ext = get_file_extension(filepath)

    if ext == ".pdf":
        return _extract_pdf(filepath)
    elif ext == ".docx":
        return _extract_docx(filepath)
    elif ext == ".txt":
        return _extract_txt(filepath)
    else:
        raise ValueError(f"Unsupported file type: {ext}")


def _extract_pdf(filepath: str) -> dict:
    """Extract text from PDF using PyMuPDF with page-level tracking."""
    doc = fitz.open(filepath)
    pages = []
    full_text_parts = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text").strip()
        if text:
            pages.append({
                "page_number": page_num + 1,
                "content": text
            })
            full_text_parts.append(text)

    page_count = len(doc)
    doc.close()

    return {
        "text": "\n\n".join(full_text_parts),
        "pages": pages,
        "page_count": page_count
    }


def _paragraph_has_page_break(paragraph) -> bool:
    """Detect an explicit or rendered page break inside a DOCX paragraph."""
    try:
        for br in paragraph._p.iter(qn("w:br")):
            if br.get(qn("w:type")) == "page":
                return True
        for _ in paragraph._p.iter(qn("w:lastRenderedPageBreak")):
            return True
    except (AttributeError, KeyError):
        return False
    return False


def _extract_docx(filepath: str) -> dict:
    """
    Extract text from DOCX using python-docx, tracking page breaks.

    DOCX has no fixed pagination, but explicit page breaks and Word's
    rendered page markers let us approximate pages for citations.
    """
    doc = DocxDocument(filepath)
    paragraphs = []
    current_page_content = []
    page_num = 1
    pages = []

    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            paragraphs.append(text)
            current_page_content.append(text)

        # Close the current logical page when a page break is encountered
        if _paragraph_has_page_break(para) and current_page_content:
            pages.append({
                "page_number": page_num,
                "content": "\n".join(current_page_content),
            })
            current_page_content = []
            page_num += 1

    # Flush the final page
    if current_page_content:
        pages.append({
            "page_number": page_num,
            "content": "\n".join(current_page_content),
        })

    return {
        "text": "\n\n".join(paragraphs),
        "pages": pages,
        "page_count": len(pages) if pages else 1,
    }


def _extract_txt(filepath: str) -> dict:
    """Extract text from plain text files."""
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read().strip()

    return {
        "text": text,
        "pages": [{"page_number": 1, "content": text}],
        "page_count": 1
    }


def chunk_text(text: str, doc_id: str, doc_name: str, pages: list = None) -> list[dict]:
    """
    Split text into semantic chunks with metadata.

    Args:
        text: Full document text
        doc_id: Document identifier
        doc_name: Original filename
        pages: Optional page-level content for page number mapping

    Returns:
        List of dicts with 'text' and 'metadata' keys.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=CHUNK_SEPARATORS,
        length_function=len,
    )

    raw_chunks = splitter.split_text(text)
    page_spans = _build_page_spans(pages) if pages else None

    enriched_chunks = []
    cursor = 0
    for idx, chunk_text_content in enumerate(raw_chunks):
        # Prefer exact character-offset mapping; fall back to content overlap.
        page_number = 1
        if page_spans:
            pos = text.find(chunk_text_content, cursor)
            if pos != -1:
                cursor = pos + 1
                page_number = _page_for_offset(pos, page_spans)
            else:
                page_number = _find_page_number(chunk_text_content, pages)

        enriched_chunks.append({
            "text": chunk_text_content,
            "metadata": {
                "doc_id": doc_id,
                "doc_name": doc_name,
                "chunk_index": idx,
                "page_number": page_number,
                "char_count": len(chunk_text_content),
            }
        })

    return enriched_chunks


def _build_page_spans(pages: list) -> list[tuple[int, int, int]]:
    """
    Build (start, end, page_number) character spans.

    Page contents are concatenated with the same "\\n\\n" separator used by
    the extractors, so offsets line up with the full document text.
    """
    spans = []
    offset = 0
    for page in pages:
        content = page.get("content", "")
        spans.append((offset, offset + len(content), page.get("page_number", 1)))
        offset += len(content) + 2  # account for the "\n\n" join separator
    return spans


def _page_for_offset(offset: int, page_spans: list[tuple[int, int, int]]) -> int:
    """Return the page number containing a character offset."""
    for start, end, page_number in page_spans:
        if start <= offset <= end:
            return page_number
    if not page_spans:
        return 1
    return page_spans[-1][2]


def _find_page_number(chunk_text: str, pages: list) -> int:
    """Find the most likely page number for a chunk by content overlap."""
    if not pages:
        return 1

    best_page = 1
    best_overlap = 0

    # Use the first 100 characters of the chunk to find the matching page
    search_snippet = chunk_text[:100]

    for page in pages:
        if search_snippet in page["content"]:
            return page["page_number"]
        # Fallback: rough character overlap
        overlap = len(set(chunk_text[:200].split()) & set(page["content"].split()))
        if overlap > best_overlap:
            best_overlap = overlap
            best_page = page["page_number"]

    return best_page
