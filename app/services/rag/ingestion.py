"""Ingestion pipeline: upload -> validate -> store -> extract -> chunk ->
embed -> index. Each stage raises a distinct, documented exception on
failure (Phase 15) and updates DocumentStatus so callers can poll status.
"""

from __future__ import annotations

import logging
import time

from app.core.config import Settings
from app.core.exceptions import DocumentProcessingError, DocumentValidationError
from app.core.logging import get_logger, log_event
from app.schemas.documents import DocumentMetadata, DocumentStatus
from app.services.ai.base import AIService
from app.services.rag.chunking import build_chunks
from app.services.rag.extraction import extract_text
from app.services.rag.validation import validate_upload
from app.services.storage.document_store import DocumentStore, new_document_id
from app.services.storage.vector_store import VectorStore

logger = get_logger(__name__)


class IngestionResult:
    def __init__(self, metadata: DocumentMetadata, chunk_count: int):
        self.metadata = metadata
        self.chunk_count = chunk_count


class IngestionPipeline:
    def __init__(
        self,
        *,
        document_store: DocumentStore,
        vector_store: VectorStore,
        ai_service: AIService,
        settings: Settings,
    ):
        self._documents = document_store
        self._vectors = vector_store
        self._ai = ai_service
        self._settings = settings
        # In a real deployment this registry would be a database
        # (e.g. Firestore/Cloud SQL); kept in-memory here to avoid adding
        # an unjustified dependency for a portfolio-scale demo. Swapping
        # it for a real repository is a small, isolated change.
        self._registry: dict[str, DocumentMetadata] = {}

    def get_status(self, document_id: str) -> DocumentMetadata | None:
        return self._registry.get(document_id)

    def ingest(
        self,
        *,
        filename: str,
        content: bytes,
        tenant_id: str | None = None,
    ) -> IngestionResult:
        document_id = new_document_id()
        start = time.perf_counter()

        try:
            content_type = validate_upload(filename, content, self._settings.upload)
        except DocumentValidationError as exc:
            log_event(
                logger, logging.WARNING, "upload_rejected", filename=filename, reason=str(exc)
            )
            raise

        metadata = DocumentMetadata(
            document_id=document_id,
            filename=filename,
            content_type=content_type,
            size_bytes=len(content),
            tenant_id=tenant_id,
            status=DocumentStatus.PROCESSING,
        )
        self._registry[document_id] = metadata

        try:
            source = self._documents.save(document_id, filename, content)
            pages = extract_text(content, content_type)

            chunks = build_chunks(
                pages,
                document_id=document_id,
                filename=filename,
                source=source,
                tenant_id=tenant_id,
                chunk_size_tokens=self._settings.retrieval.chunk_size_tokens,
                chunk_overlap_tokens=self._settings.retrieval.chunk_overlap_tokens,
            )
            if not chunks:
                raise DocumentProcessingError("No chunks produced from document.")

            metadata.status = DocumentStatus.EMBEDDING
            embeddings = self._embed_in_batches([c.text for c in chunks])

            self._vectors.upsert(chunks, embeddings)
            metadata.status = DocumentStatus.INDEXED

            log_event(
                logger,
                logging.INFO,
                "document_ingested",
                document_id=document_id,
                chunk_count=len(chunks),
                duration_ms=round((time.perf_counter() - start) * 1000, 1),
            )
            return IngestionResult(metadata=metadata, chunk_count=len(chunks))

        except Exception as exc:
            metadata.status = DocumentStatus.FAILED
            metadata.error_message = str(exc)
            log_event(
                logger, logging.ERROR, "ingestion_failed", document_id=document_id, error=str(exc)
            )
            raise

    def _embed_in_batches(self, texts: list[str]) -> list[list[float]]:
        batch_size = self._settings.embedding.batch_size
        vectors: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            result = self._ai.embed_texts(batch)
            vectors.extend(result.vectors)
        return vectors
