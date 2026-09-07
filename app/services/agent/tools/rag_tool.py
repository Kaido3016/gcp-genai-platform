"""RAG search tool: lets the agent query the same vector store the /chat
endpoint uses, so both surfaces share one retrieval implementation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.core.config import RetrievalConfig
from app.schemas.agent import RagSearchArgs, ToolName
from app.services.agent.tools.base import Tool
from app.services.ai.base import AIService
from app.services.rag.retrieval import filter_and_rank
from app.services.storage.vector_store import VectorStore


class RagSearchTool(Tool):
    name = ToolName.RAG_SEARCH
    description = (
        "Search the ingested document corpus for passages relevant to a "
        "query. Returns ranked text snippets with source metadata. Use "
        "this whenever the user asks about content from uploaded documents."
    )
    allowed_for_all = True

    def __init__(
        self, ai_service: AIService, vector_store: VectorStore, retrieval_config: RetrievalConfig
    ):
        self._ai = ai_service
        self._vectors = vector_store
        self._config = retrieval_config

    def run(self, args: BaseModel, *, context: dict[str, Any]) -> Any:
        assert isinstance(args, RagSearchArgs)
        embedding = self._ai.embed_texts([args.query]).vectors[0]
        candidates = self._vectors.query(
            embedding, top_k=args.top_k, tenant_id=context.get("tenant_id")
        )
        ranked = filter_and_rank(candidates, self._config)
        return [
            {
                "text": rc.chunk.text,
                "filename": rc.chunk.filename,
                "page": rc.chunk.page,
                "similarity_score": round(rc.similarity_score, 4),
                "document_id": rc.chunk.document_id,
                "chunk_id": rc.chunk.chunk_id,
            }
            for rc in ranked
        ]
