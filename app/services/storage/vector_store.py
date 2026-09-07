"""Vector store abstraction."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod

from app.core.exceptions import VectorStoreError
from app.schemas.documents import Chunk, RetrievedChunk


class VectorStore(ABC):
    @abstractmethod
    def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None: ...

    @abstractmethod
    def query(
        self,
        vector: list[float],
        *,
        top_k: int,
        tenant_id: str | None = None,
        document_id: str | None = None,
    ) -> list[RetrievedChunk]: ...

    @abstractmethod
    def delete_document(self, document_id: str) -> int:
        """Deletes all chunks for a document; returns count deleted."""


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise VectorStoreError("Vector dimension mismatch during similarity computation.")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    cos = dot / (norm_a * norm_b)
    return max(cos, 0.0)


class InMemoryVectorStore(VectorStore):
    """Reference/test implementation using an O(n) linear scan."""

    def __init__(self) -> None:
        self._chunks: dict[str, Chunk] = {}
        self._vectors: dict[str, list[float]] = {}

    def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        if len(chunks) != len(vectors):
            raise VectorStoreError("chunks and vectors must be the same length.")
        for chunk, vector in zip(chunks, vectors, strict=True):
            self._chunks[chunk.chunk_id] = chunk
            self._vectors[chunk.chunk_id] = vector

    def query(
        self,
        vector: list[float],
        *,
        top_k: int,
        tenant_id: str | None = None,
        document_id: str | None = None,
    ) -> list[RetrievedChunk]:
        scored: list[RetrievedChunk] = []
        for chunk_id, chunk in self._chunks.items():
            if tenant_id is not None and chunk.tenant_id != tenant_id:
                continue
            if document_id is not None and chunk.document_id != document_id:
                continue
            score = _cosine_similarity(vector, self._vectors[chunk_id])
            scored.append(RetrievedChunk(chunk=chunk, similarity_score=score))
        scored.sort(key=lambda rc: rc.similarity_score, reverse=True)
        return scored[:top_k]

    def delete_document(self, document_id: str) -> int:
        ids = [cid for cid, c in self._chunks.items() if c.document_id == document_id]
        for cid in ids:
            del self._chunks[cid]
            del self._vectors[cid]
        return len(ids)


class VertexVectorSearchStore(VectorStore):
    """Live Vertex AI Vector Search adapter."""

    def __init__(self, *, project: str, location: str, index_id: str, index_endpoint_id: str):
        try:
            from google.cloud import aiplatform  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise VectorStoreError(
                "google-cloud-aiplatform is not installed. Run "
                "`pip install google-cloud-aiplatform`."
            ) from exc

        aiplatform.init(project=project, location=location)
        self._aiplatform = aiplatform
        self._index = aiplatform.MatchingEngineIndex(index_id)
        self._endpoint = aiplatform.MatchingEngineIndexEndpoint(index_endpoint_id)
        self._deployed_index_id = index_id
        self._metadata_lookup: dict[str, Chunk] = {}

    def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        datapoints = [
            {"datapoint_id": chunk.chunk_id, "feature_vector": vector}
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        try:
            self._index.upsert_datapoints(datapoints=datapoints)
        except Exception as exc:
            raise VectorStoreError(f"Vector Search upsert failed: {exc}") from exc
        for chunk in chunks:
            self._metadata_lookup[chunk.chunk_id] = chunk

    def query(
        self,
        vector: list[float],
        *,
        top_k: int,
        tenant_id: str | None = None,
        document_id: str | None = None,
    ) -> list[RetrievedChunk]:
        try:
            response = self._endpoint.find_neighbors(
                deployed_index_id=self._deployed_index_id,
                queries=[vector],
                num_neighbors=top_k,
            )
        except Exception as exc:
            raise VectorStoreError(f"Vector Search query failed: {exc}") from exc

        results: list[RetrievedChunk] = []
        for neighbor in response[0]:
            chunk = self._metadata_lookup.get(neighbor.id)
            if not chunk:
                continue
            if tenant_id is not None and chunk.tenant_id != tenant_id:
                continue
            if document_id is not None and chunk.document_id != document_id:
                continue
            similarity = 1.0 - (neighbor.distance / 2.0)
            results.append(RetrievedChunk(chunk=chunk, similarity_score=similarity))
        return results

    def delete_document(self, document_id: str) -> int:
        ids = [cid for cid, c in self._metadata_lookup.items() if c.document_id == document_id]
        if not ids:
            return 0
        try:
            self._index.remove_datapoints(datapoint_ids=ids)
        except Exception as exc:
            raise VectorStoreError(f"Vector Search delete failed: {exc}") from exc
        for cid in ids:
            del self._metadata_lookup[cid]
        return len(ids)
