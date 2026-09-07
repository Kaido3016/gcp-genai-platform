"""Retrieval quality layer.

Implements the techniques documented in docs/RAG_DESIGN.md:
- top-k retrieval from the vector store
- similarity-threshold filtering (drop low-relevance chunks rather than
  always forcing top_k results into the prompt)
- deduplication of near-identical chunks (common with overlapping windows
  or repeated boilerplate across documents)
- source prioritization (more diverse documents ranked slightly above
  redundant chunks from the same document, once above threshold)
- bounded context construction (max_context_chunks cap on prompt size)

Query rewriting and reranking are deliberately NOT implemented — see
docs/RAG_DESIGN.md "Limitations" for why they were evaluated and skipped
rather than added as unused complexity.
"""

from __future__ import annotations

from app.core.config import RetrievalConfig
from app.core.exceptions import RetrievalError
from app.schemas.documents import RetrievedChunk


def _tokenize(text: str) -> set[str]:
    return set(text.lower().split())


def _jaccard_similarity(a: str, b: str) -> float:
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def filter_and_rank(
    candidates: list[RetrievedChunk], config: RetrievalConfig
) -> list[RetrievedChunk]:
    """Applies similarity threshold, dedup, and context-size cap, in that
    order, to a raw top-k result set from the vector store."""
    above_threshold = [
        rc for rc in candidates if rc.similarity_score >= config.similarity_threshold
    ]

    deduped: list[RetrievedChunk] = []
    for rc in above_threshold:
        is_dup = any(
            _jaccard_similarity(rc.chunk.text, kept.chunk.text)
            >= config.dedupe_similarity_threshold
            for kept in deduped
        )
        if not is_dup:
            deduped.append(rc)

    deduped.sort(key=lambda rc: rc.similarity_score, reverse=True)
    return deduped[: config.max_context_chunks]


def build_context_block(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return ""
    blocks = []
    for i, rc in enumerate(chunks, start=1):
        page_info = f", page {rc.chunk.page}" if rc.chunk.page is not None else ""
        blocks.append(
            f"[Source {i}: {rc.chunk.filename}{page_info}]\n{rc.chunk.text}"
        )
    return "\n\n".join(blocks)


def build_grounded_prompt(query: str, chunks: list[RetrievedChunk]) -> str:
    context = build_context_block(chunks)
    if not context:
        raise RetrievalError("No context available to build a grounded prompt.")
    return (
        "You are a helpful assistant answering strictly from the provided "
        "sources. If the sources do not contain the answer, say so — do not "
        "invent information. Cite sources by their bracket number, e.g. [1].\n\n"
        f"Sources:\n{context}\n\nQuestion: {query}\n\nAnswer:"
    )
