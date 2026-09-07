from app.schemas.documents import Chunk


def _seed(vector_store, ai_service, texts, document_id="doc-1", filename="doc.txt"):
    chunks = [
        Chunk(document_id=document_id, filename=filename, text=t, source=filename, page=i + 1)
        for i, t in enumerate(texts)
    ]
    vectors = [ai_service.embed_texts([t]).vectors[0] for t in texts]
    vector_store.upsert(chunks, vectors)
    return chunks


def test_answer_is_grounded_when_relevant_chunks_exist(rag_pipeline, vector_store, ai_service):
    _seed(
        vector_store,
        ai_service,
        [
            "Vertex AI Vector Search provides low-latency approximate nearest neighbor search.",
            "Cloud Run is a fully managed serverless platform for containers.",
        ],
    )
    response = rag_pipeline.answer("What does Vertex AI Vector Search provide?")
    assert response.grounded is True
    assert response.retrieved_chunk_count >= 1
    assert len(response.citations) >= 1
    assert response.citations[0].filename == "doc.txt"


def test_answer_falls_back_ungrounded_when_no_documents_indexed(rag_pipeline):
    response = rag_pipeline.answer("What is in the knowledge base?")
    assert response.grounded is False
    assert response.citations == []
    assert response.retrieved_chunk_count == 0


def test_citations_carry_full_provenance(rag_pipeline, vector_store, ai_service):
    _seed(
        vector_store,
        ai_service,
        ["Gemini supports multimodal input including text, images, and PDFs."],
        document_id="doc-42",
        filename="gemini_overview.txt",
    )
    response = rag_pipeline.answer("What input types does Gemini support?")
    assert response.grounded is True
    citation = response.citations[0]
    assert citation.document_id == "doc-42"
    assert citation.filename == "gemini_overview.txt"
    assert citation.chunk_id
    assert 0.0 <= citation.similarity_score <= 1.0


def test_latency_is_measured_and_positive(rag_pipeline, vector_store, ai_service):
    _seed(vector_store, ai_service, ["Some content for latency measurement."])
    response = rag_pipeline.answer("What content exists?")
    assert response.latency_ms >= 0.0
