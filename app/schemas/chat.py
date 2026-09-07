"""RAG chat request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.schemas.documents import RetrievedChunk


class Citation(BaseModel):
    document_id: str
    filename: str
    chunk_id: str
    page: int | None = None
    similarity_score: float


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    tenant_id: str | None = None
    conversation_id: str | None = None

    @field_validator("query")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("query must not be blank")
        return v


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    grounded: bool = Field(
        description="True if the answer was produced from retrieved context "
        "above the similarity threshold; False if the model fell back to "
        "answering without sufficient grounded context."
    )
    retrieved_chunk_count: int
    model_used: str
    latency_ms: float
    conversation_id: str | None = None


def citations_from_chunks(chunks: list[RetrievedChunk]) -> list[Citation]:
    return [
        Citation(
            document_id=rc.chunk.document_id,
            filename=rc.chunk.filename,
            chunk_id=rc.chunk.chunk_id,
            page=rc.chunk.page,
            similarity_score=rc.similarity_score,
        )
        for rc in chunks
    ]
