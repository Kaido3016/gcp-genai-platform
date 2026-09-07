import pytest

from app.core.exceptions import DocumentProcessingError, DocumentValidationError
from app.schemas.documents import DocumentStatus


def test_ingest_txt_document_end_to_end(ingestion_pipeline, vector_store):
    content = b"Vertex AI is Google Cloud's managed machine learning platform.\n\nIt supports Gemini models."
    result = ingestion_pipeline.ingest(filename="notes.txt", content=content, tenant_id="tenant-1")

    assert result.metadata.status == DocumentStatus.INDEXED
    assert result.chunk_count >= 1

    status = ingestion_pipeline.get_status(result.metadata.document_id)
    assert status is not None
    assert status.status == DocumentStatus.INDEXED

    # Vector store should actually contain the chunks with correct provenance.
    indexed = vector_store.query([0.0] * 768, top_k=10, document_id=result.metadata.document_id)
    assert len(indexed) == result.chunk_count
    for rc in indexed:
        assert rc.chunk.document_id == result.metadata.document_id
        assert rc.chunk.filename == "notes.txt"
        assert rc.chunk.tenant_id == "tenant-1"


def test_ingest_rejects_disallowed_extension(ingestion_pipeline):
    with pytest.raises(DocumentValidationError):
        ingestion_pipeline.ingest(filename="malware.exe", content=b"MZ\x90\x00", tenant_id=None)


def test_ingest_marks_status_failed_on_extraction_error(ingestion_pipeline):
    # A .pdf extension with content that doesn't start with %PDF- is rejected
    # by validation before extraction is even attempted (defense in depth).
    with pytest.raises(DocumentValidationError):
        ingestion_pipeline.ingest(filename="fake.pdf", content=b"not a real pdf", tenant_id=None)


def test_ingest_empty_pdf_text_marks_failed_status(ingestion_pipeline, monkeypatch):
    # Simulate a validly-typed PDF that yields no extractable text (e.g.
    # scanned/image-only) by monkeypatching extract_text for this test.
    import app.services.rag.ingestion as ingestion_module

    def fake_extract_text(content, content_type):
        raise DocumentProcessingError(
            "No extractable text found in PDF (possibly scanned/image-only)."
        )

    monkeypatch.setattr(ingestion_module, "extract_text", fake_extract_text)

    with pytest.raises(DocumentProcessingError):
        ingestion_pipeline.ingest(
            filename="scanned.pdf", content=b"%PDF-1.4 minimal", tenant_id=None
        )

    # The document should be registered with FAILED status, not silently dropped.
    doc_ids = list(ingestion_pipeline._registry.keys())
    assert len(doc_ids) == 1
    failed = ingestion_pipeline.get_status(doc_ids[0])
    assert failed.status == DocumentStatus.FAILED
    assert failed.error_message is not None


def test_get_status_returns_none_for_unknown_document(ingestion_pipeline):
    assert ingestion_pipeline.get_status("does-not-exist") is None


def test_multiple_documents_are_isolated_by_tenant(ingestion_pipeline, vector_store):
    ingestion_pipeline.ingest(
        filename="a.txt", content=b"Content about apples.", tenant_id="tenant-a"
    )
    ingestion_pipeline.ingest(
        filename="b.txt", content=b"Content about bananas.", tenant_id="tenant-b"
    )

    results_a = vector_store.query([0.0] * 768, top_k=10, tenant_id="tenant-a")
    results_b = vector_store.query([0.0] * 768, top_k=10, tenant_id="tenant-b")
    assert all(rc.chunk.tenant_id == "tenant-a" for rc in results_a)
    assert all(rc.chunk.tenant_id == "tenant-b" for rc in results_b)
    assert len(results_a) == 1
    assert len(results_b) == 1
