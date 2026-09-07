from app.core.config import RetrievalConfig
from app.schemas.documents import Chunk, RetrievedChunk
from app.services.rag.retrieval import build_context_block, build_grounded_prompt, filter_and_rank


def _rc(chunk_id: str, text: str, score: float, page: int | None = None) -> RetrievedChunk:
    chunk = Chunk(
        chunk_id=chunk_id, document_id="d1", filename="f.txt", text=text, source="s", page=page
    )
    return RetrievedChunk(chunk=chunk, similarity_score=score)


def test_filters_below_threshold():
    config = RetrievalConfig(
        similarity_threshold=0.6, max_context_chunks=10, dedupe_similarity_threshold=0.97
    )
    candidates = [_rc("c1", "alpha bravo charlie", 0.9), _rc("c2", "delta echo foxtrot", 0.3)]
    result = filter_and_rank(candidates, config)
    assert len(result) == 1
    assert result[0].chunk.chunk_id == "c1"


def test_deduplicates_near_identical_chunks():
    config = RetrievalConfig(
        similarity_threshold=0.0, max_context_chunks=10, dedupe_similarity_threshold=0.9
    )
    candidates = [
        _rc("c1", "the quick brown fox jumps over the lazy dog", 0.95),
        _rc("c2", "the quick brown fox jumps over the lazy dog!", 0.90),
        _rc("c3", "completely unrelated different content here", 0.85),
    ]
    result = filter_and_rank(candidates, config)
    ids = {rc.chunk.chunk_id for rc in result}
    assert "c1" in ids
    assert "c2" not in ids  # near-duplicate of c1, dropped
    assert "c3" in ids


def test_caps_at_max_context_chunks():
    config = RetrievalConfig(
        similarity_threshold=0.0, max_context_chunks=2, dedupe_similarity_threshold=0.97
    )
    candidates = [_rc(f"c{i}", f"unique text block number {i}", 0.5 + i * 0.01) for i in range(5)]
    result = filter_and_rank(candidates, config)
    assert len(result) == 2
    # highest scores kept
    assert result[0].similarity_score >= result[1].similarity_score


def test_build_context_block_includes_page_info():
    chunks = [_rc("c1", "some text", 0.9, page=3)]
    block = build_context_block(chunks)
    assert "page 3" in block
    assert "some text" in block


def test_build_context_block_empty_for_no_chunks():
    assert build_context_block([]) == ""


def test_build_grounded_prompt_raises_on_empty_context():
    import pytest

    from app.core.exceptions import RetrievalError

    with pytest.raises(RetrievalError):
        build_grounded_prompt("what is x?", [])


def test_build_grounded_prompt_includes_query_and_sources():
    chunks = [_rc("c1", "relevant fact", 0.9)]
    prompt = build_grounded_prompt("What is the fact?", chunks)
    assert "What is the fact?" in prompt
    assert "relevant fact" in prompt
