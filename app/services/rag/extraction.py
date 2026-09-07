"""Text extraction per document type.

Returns a list of (page_number_or_None, text) tuples so page metadata can
be preserved through chunking (Phase 4 requirement: retrieved sources must
carry page numbers where applicable).
"""

from __future__ import annotations

from app.core.exceptions import DocumentProcessingError


def extract_text(content: bytes, content_type: str) -> list[tuple[int | None, str]]:
    if content_type == "text/plain" or content_type == "text/markdown":
        return [(None, content.decode("utf-8", errors="replace"))]

    if content_type == "application/pdf":
        return _extract_pdf(content)

    if content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return _extract_docx(content)

    raise DocumentProcessingError(f"Unsupported content type for extraction: {content_type}")


def _extract_pdf(content: bytes) -> list[tuple[int | None, str]]:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError as exc:
        raise DocumentProcessingError(
            "pypdf is not installed. Run `pip install pypdf` to enable PDF extraction."
        ) from exc

    import io

    try:
        reader = PdfReader(io.BytesIO(content))
        pages = []
        for i, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                pages.append((i, text))
        if not pages:
            raise DocumentProcessingError(
                "No extractable text found in PDF (possibly scanned/image-only)."
            )
        return pages
    except DocumentProcessingError:
        raise
    except Exception as exc:
        raise DocumentProcessingError(f"Failed to parse PDF: {exc}") from exc


def _extract_docx(content: bytes) -> list[tuple[int | None, str]]:
    try:
        import docx  # type: ignore
    except ImportError as exc:
        raise DocumentProcessingError(
            "python-docx is not installed. Run `pip install python-docx` to enable .docx extraction."
        ) from exc

    import io

    try:
        document = docx.Document(io.BytesIO(content))
        text = "\n".join(p.text for p in document.paragraphs)
        if not text.strip():
            raise DocumentProcessingError("No extractable text found in .docx file.")
        return [(None, text)]
    except DocumentProcessingError:
        raise
    except Exception as exc:
        raise DocumentProcessingError(f"Failed to parse .docx: {exc}") from exc
