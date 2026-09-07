"""Schemas for document ingestion and retrieved chunk metadata (Phase 4)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    VALIDATING = "validating"
    PROCESSING = "processing"
    EMBEDDING = "embedding"
    INDEXED = "indexed"
    FAILED = "failed"


class DocumentMetadata(BaseModel):
    document_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    filename: str
    content_type: str
    size_bytes: int
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    tenant_id: str | None = Field(
        default=None, description="Owning user/tenant, for scoped retrieval."
    )
    status: DocumentStatus = DocumentStatus.UPLOADED
    error_message: str | None = None


class Chunk(BaseModel):
    """A single retrievable unit, carrying full provenance metadata."""

    chunk_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    document_id: str
    filename: str
    page: int | None = None
    text: str
    source: str = Field(description="e.g. gs://bucket/path or original filename")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    tenant_id: str | None = None
    token_count: int = 0


class RetrievedChunk(BaseModel):
    chunk: Chunk
    similarity_score: float = Field(ge=0.0, le=1.0)


class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    status: DocumentStatus
    message: str


class DocumentStatusResponse(BaseModel):
    metadata: DocumentMetadata
    chunk_count: int = 0
