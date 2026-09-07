"""Chunking strategy.

Documented in docs/RAG_DESIGN.md: fixed-size word-based windows with
overlap, approximating token count via whitespace splitting. This avoids
pulling in a tokenizer dependency just for chunk boundaries — good enough
because the embedding model's own tokenizer will be the ground truth at
embedding time, and the overlap absorbs boundary information loss.
Paragraph-aware splitting is used first so chunks don't split mid-sentence
where possible.
"""

from __future__ import annotations

import re

from app.schemas.documents import Chunk


def _approx_token_count(text: str) -> int:
    return len(text.split())


def chunk_page_text(
    text: str,
    *,
    chunk_size_tokens: int,
    chunk_overlap_tokens: int,
) -> list[str]:
    """Splits a page/document's text into overlapping chunks, preferring
    paragraph boundaries and falling back to a sliding word window."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        paragraphs = [text.strip()] if text.strip() else []

    chunks: list[str] = []
    current_words: list[str] = []

    for para in paragraphs:
        para_words = para.split()
        if len(current_words) + len(para_words) <= chunk_size_tokens:
            current_words.extend(para_words)
            continue

        if current_words:
            chunks.append(" ".join(current_words))
            overlap = current_words[-chunk_overlap_tokens:] if chunk_overlap_tokens else []
            current_words = overlap

        # If a single paragraph itself exceeds chunk_size, hard-split it.
        while len(para_words) > chunk_size_tokens:
            window = para_words[:chunk_size_tokens]
            chunks.append(" ".join(current_words + window) if current_words else " ".join(window))
            current_words = []
            step = max(chunk_size_tokens - chunk_overlap_tokens, 1)
            para_words = para_words[step:]

        current_words.extend(para_words)

    if current_words:
        chunks.append(" ".join(current_words))

    return chunks


def build_chunks(
    pages: list[tuple[int | None, str]],
    *,
    document_id: str,
    filename: str,
    source: str,
    tenant_id: str | None,
    chunk_size_tokens: int,
    chunk_overlap_tokens: int,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for page_number, page_text in pages:
        for piece in chunk_page_text(
            page_text,
            chunk_size_tokens=chunk_size_tokens,
            chunk_overlap_tokens=chunk_overlap_tokens,
        ):
            chunks.append(
                Chunk(
                    document_id=document_id,
                    filename=filename,
                    page=page_number,
                    text=piece,
                    source=source,
                    tenant_id=tenant_id,
                    token_count=_approx_token_count(piece),
                )
            )
    return chunks
