"""End-to-end RAG query pipeline used by the /chat endpoint."""

from __future__ import annotations

import logging
import time

from app.core.config import Settings
from app.core.logging import get_logger, log_event
from app.schemas.chat import ChatResponse, citations_from_chunks
from app.services.ai.base import AIService
from app.services.rag.retrieval import build_grounded_prompt, filter_and_rank
from app.services.storage.vector_store import VectorStore

logger = get_logger(__name__)


class RagPipeline:
    def __init__(self, *, ai_service: AIService, vector_store: VectorStore, settings: Settings):
        self._ai = ai_service
        self._vectors = vector_store
        self._settings = settings

    def answer(self, query: str, *, tenant_id: str | None = None) -> ChatResponse:
        start = time.perf_counter()
        retrieval_cfg = self._settings.retrieval

        embedding = self._ai.embed_texts([query]).vectors[0]
        candidates = self._vectors.query(
            embedding, top_k=retrieval_cfg.top_k, tenant_id=tenant_id
        )
        ranked = filter_and_rank(candidates, retrieval_cfg)

        if not ranked:
            log_event(logger, logging.INFO, "rag_no_grounded_context", query_len=len(query))
            result = self._ai.generate_text(
                f"Answer helpfully, but note no supporting documents were found for: {query}"
            )
            return ChatResponse(
                answer=result.text,
                citations=[],
                grounded=False,
                retrieved_chunk_count=0,
                model_used=result.model,
                latency_ms=round((time.perf_counter() - start) * 1000, 1),
            )

        prompt = build_grounded_prompt(query, ranked)
        result = self._ai.generate_text(prompt)

        log_event(
            logger,
            logging.INFO,
            "rag_answer_generated",
            retrieved_chunks=len(ranked),
            duration_ms=round((time.perf_counter() - start) * 1000, 1),
        )
        return ChatResponse(
            answer=result.text,
            citations=citations_from_chunks(ranked),
            grounded=True,
            retrieved_chunk_count=len(ranked),
            model_used=result.model,
            latency_ms=round((time.perf_counter() - start) * 1000, 1),
        )
