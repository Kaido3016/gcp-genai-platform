from app.schemas.documents import Chunk
from app.services.storage.vector_store import InMemoryVectorStore


def _chunk(chunk_id: str, document_id: str, tenant_id: str | None = None) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        document_id=document_id,
        filename="f.txt",
        text="some text",
        source="src",
        tenant_id=tenant_id,
    )


def test_upsert_and_query_returns_closest_first():
    store = InMemoryVectorStore()
    c1 = _chunk("c1", "d1")
    c2 = _chunk("c2", "d1")
    store.upsert([c1, c2], [[1.0, 0.0], [0.0, 1.0]])

    results = store.query([1.0, 0.0], top_k=2)
    assert len(results) == 2
    assert results[0].chunk.chunk_id == "c1"
    assert results[0].similarity_score > results[1].similarity_score


def test_query_respects_top_k():
    store = InMemoryVectorStore()
    chunks = [_chunk(f"c{i}", "d1") for i in range(5)]
    vectors = [[float(i), 1.0] for i in range(5)]
    store.upsert(chunks, vectors)

    results = store.query([0.0, 1.0], top_k=2)
    assert len(results) == 2


def test_query_filters_by_tenant():
    store = InMemoryVectorStore()
    c1 = _chunk("c1", "d1", tenant_id="tenant-a")
    c2 = _chunk("c2", "d1", tenant_id="tenant-b")
    store.upsert([c1, c2], [[1.0, 0.0], [1.0, 0.0]])

    results = store.query([1.0, 0.0], top_k=10, tenant_id="tenant-a")
    assert len(results) == 1
    assert results[0].chunk.chunk_id == "c1"


def test_delete_document_removes_its_chunks():
    store = InMemoryVectorStore()
    c1 = _chunk("c1", "d1")
    c2 = _chunk("c2", "d2")
    store.upsert([c1, c2], [[1.0, 0.0], [0.0, 1.0]])

    deleted = store.delete_document("d1")
    assert deleted == 1
    results = store.query([1.0, 0.0], top_k=10)
    assert all(rc.chunk.document_id != "d1" for rc in results)
