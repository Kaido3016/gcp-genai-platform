from app.services.rag.chunking import build_chunks, chunk_page_text


def test_chunk_page_text_respects_size_limit():
    text = "word " * 1000
    chunks = chunk_page_text(text, chunk_size_tokens=100, chunk_overlap_tokens=10)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c.split()) <= 110  # allow slack for paragraph grouping edge cases


def test_chunk_page_text_overlap_present():
    text = "\n\n".join([f"sentence number {i} with some extra words padding" for i in range(50)])
    chunks = chunk_page_text(text, chunk_size_tokens=40, chunk_overlap_tokens=10)
    assert len(chunks) >= 2
    # last words of chunk N should reappear at the start of chunk N+1
    first_chunk_tail = chunks[0].split()[-5:]
    second_chunk_head = chunks[1].split()[:20]
    assert any(word in second_chunk_head for word in first_chunk_tail)


def test_chunk_page_text_empty_returns_empty():
    assert chunk_page_text("", chunk_size_tokens=100, chunk_overlap_tokens=10) == []


def test_build_chunks_preserves_page_and_metadata():
    pages = [(1, "first page text here"), (2, "second page text here")]
    chunks = build_chunks(
        pages,
        document_id="doc-1",
        filename="test.pdf",
        source="/tmp/test.pdf",
        tenant_id="tenant-a",
        chunk_size_tokens=100,
        chunk_overlap_tokens=10,
    )
    assert len(chunks) == 2
    assert chunks[0].page == 1
    assert chunks[1].page == 2
    assert all(c.document_id == "doc-1" for c in chunks)
    assert all(c.tenant_id == "tenant-a" for c in chunks)
    assert all(c.token_count > 0 for c in chunks)
