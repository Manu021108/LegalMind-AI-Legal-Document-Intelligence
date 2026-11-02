"""
Utility helpers for the Legal Document Analyzer.
"""

import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from config import ALLOWED_EXTENSIONS


def generate_id() -> str:
    """Generate a unique ID."""
    return str(uuid.uuid4())


def get_timestamp() -> str:
    """Get current UTC timestamp as ISO string."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_file_extension(filename: str) -> bool:
    """Check if the file extension is allowed."""
    ext = Path(filename).suffix.lower()
    return ext in ALLOWED_EXTENSIONS


def get_file_extension(filename: str) -> str:
    """Get the lowercase file extension."""
    return Path(filename).suffix.lower()


def safe_filename(filename: str) -> str:
    """Sanitize a filename to prevent path traversal."""
    name = Path(filename).name
    # Remove any problematic characters
    safe = "".join(c for c in name if c.isalnum() or c in "._- ")
    # Strip leading dots so hidden/relative names cannot be created
    safe = safe.lstrip(".").strip()
    return safe if safe else "unnamed_document"


def is_path_within(base_dir, candidate) -> bool:
    """Return True if `candidate` resolves to a path inside `base_dir`."""
    try:
        base = Path(base_dir).resolve()
        target = Path(candidate).resolve()
    except (OSError, ValueError):
        return False
    return target == base or base in target.parents


def validate_file_content(filepath: str, ext: str) -> tuple[bool, str]:
    """
    Validate that a file's content matches its declared extension.

    Guards against executables/scripts renamed with a legal-document
    extension. Returns (is_valid, reason).
    """
    ext = (ext or "").lower()

    try:
        if ext == ".pdf":
            with open(filepath, "rb") as f:
                header = f.read(5)
            if header != b"%PDF-":
                return False, "File does not appear to be a valid PDF."
            return True, ""

        if ext == ".docx":
            if not zipfile.is_zipfile(filepath):
                return False, "File does not appear to be a valid DOCX."
            try:
                with zipfile.ZipFile(filepath) as archive:
                    names = set(archive.namelist())
            except zipfile.BadZipFile:
                return False, "File does not appear to be a valid DOCX."
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                return False, "File does not appear to be a valid DOCX."
            return True, ""

        if ext == ".txt":
            with open(filepath, "rb") as f:
                sample = f.read(65536)
            if b"\x00" in sample:
                return False, "Text file contains binary data."
            for encoding in ("utf-8", "utf-16", "cp1252"):
                try:
                    sample.decode(encoding)
                    return True, ""
                except UnicodeDecodeError:
                    continue
            return False, "File does not appear to be plain text."

    except OSError:
        return False, "File could not be read for validation."

    return False, f"Unsupported file type: {ext}"


def truncate_text(text: str, max_length: int = 150) -> str:
    """Truncate text with ellipsis for previews."""
    if len(text) <= max_length:
        return text
    return text[:max_length].rsplit(" ", 1)[0] + "..."


def format_file_size(size_bytes: int) -> str:
    """Format bytes to human-readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
