"""Upload validation: file type, size limits, and basic content sanity
checks. This is a security control (Phase 13), not just a UX nicety —
unvalidated uploads are the most common RAG attack surface.
"""

from __future__ import annotations

from pathlib import Path

from app.core.config import UploadConfig
from app.core.exceptions import DocumentValidationError

_MIME_BY_EXTENSION = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def validate_upload(filename: str, content: bytes, config: UploadConfig) -> str:
    """Returns the resolved content_type, or raises DocumentValidationError."""
    if not filename or "/" in filename or "\\" in filename:
        raise DocumentValidationError("Invalid filename.")

    ext = Path(filename).suffix.lower()
    if ext not in config.allowed_extensions:
        raise DocumentValidationError(
            f"File type '{ext}' is not allowed. Allowed: {config.allowed_extensions}"
        )

    size_mb = len(content) / (1024 * 1024)
    if size_mb > config.max_file_size_mb:
        raise DocumentValidationError(
            f"File is {size_mb:.1f}MB, exceeds the {config.max_file_size_mb}MB limit."
        )

    if len(content) == 0:
        raise DocumentValidationError("File is empty.")

    # Minimal magic-byte sanity check to catch obviously mislabeled files
    # (defense in depth against extension spoofing).
    if ext == ".pdf" and not content.startswith(b"%PDF-"):
        raise DocumentValidationError("File has a .pdf extension but is not a valid PDF.")

    return _MIME_BY_EXTENSION[ext]
