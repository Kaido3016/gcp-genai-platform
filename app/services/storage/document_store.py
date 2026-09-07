"""Blob storage abstraction for uploaded source documents.

Same pattern as the vector store: a live Cloud Storage backend for
production, a local-filesystem backend for this offline environment and
for fast tests, both behind one interface.
"""

from __future__ import annotations

import os
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from app.core.exceptions import DocumentProcessingError


class DocumentStore(ABC):
    @abstractmethod
    def save(self, document_id: str, filename: str, content: bytes) -> str:
        """Persists raw bytes; returns a source URI/path."""

    @abstractmethod
    def read(self, source: str) -> bytes: ...

    @abstractmethod
    def delete(self, source: str) -> None: ...


class LocalDocumentStore(DocumentStore):
    """Filesystem-backed store. Used when GCP_USE_LIVE_VERTEX_AI is False."""

    def __init__(self, base_dir: str | None = None):
        self._base = Path(base_dir or "/tmp/genai-platform-documents")
        self._base.mkdir(parents=True, exist_ok=True)

    def save(self, document_id: str, filename: str, content: bytes) -> str:
        safe_name = f"{document_id}__{Path(filename).name}"
        path = self._base / safe_name
        path.write_bytes(content)
        return str(path)

    def read(self, source: str) -> bytes:
        path = Path(source)
        if not path.exists():
            raise DocumentProcessingError(f"Source not found: {source}")
        return path.read_bytes()

    def delete(self, source: str) -> None:
        path = Path(source)
        if path.exists():
            os.remove(path)


class GCSDocumentStore(DocumentStore):
    """Live Cloud Storage backend. Real, runnable code, not exercised here
    without network/credentials. Requires the bucket in GCP_DOCUMENTS_BUCKET
    to exist with a least-privilege service account (see docs/SECURITY.md
    and docs/DEPLOYMENT.md) — uniform bucket-level access, no public ACLs,
    and object versioning recommended for audit/rollback.
    """

    def __init__(self, bucket_name: str):
        try:
            from google.cloud import storage  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise DocumentProcessingError(
                "google-cloud-storage is not installed. Run "
                "`pip install google-cloud-storage`."
            ) from exc
        self._client = storage.Client()
        self._bucket = self._client.bucket(bucket_name)

    def save(self, document_id: str, filename: str, content: bytes) -> str:
        blob_name = f"documents/{document_id}/{filename}"
        blob = self._bucket.blob(blob_name)
        blob.upload_from_string(content)
        return f"gs://{self._bucket.name}/{blob_name}"

    def read(self, source: str) -> bytes:
        blob_name = source.split(f"gs://{self._bucket.name}/", 1)[-1]
        blob = self._bucket.blob(blob_name)
        if not blob.exists():
            raise DocumentProcessingError(f"Source not found: {source}")
        return blob.download_as_bytes()

    def delete(self, source: str) -> None:
        blob_name = source.split(f"gs://{self._bucket.name}/", 1)[-1]
        self._bucket.blob(blob_name).delete()


def new_document_id() -> str:
    return str(uuid.uuid4())
