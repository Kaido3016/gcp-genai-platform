"""Composition root: builds and caches the service graph.

Kept in one place so tests can override individual pieces (e.g. swap in a
fake VectorStore) without touching route code — see tests/unit and
tests/integration for examples using FastAPI's dependency_overrides.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import Settings, get_settings
from app.services.agent.agent import Agent
from app.services.agent.tools.base import ToolRegistry
from app.services.agent.tools.calculator_tool import CalculatorTool
from app.services.agent.tools.mcp_tool import McpCurrentDatetimeTool, McpTextStatsTool
from app.services.agent.tools.rag_tool import RagSearchTool
from app.services.ai.base import AIService
from app.services.ai.service import build_ai_service
from app.services.rag.ingestion import IngestionPipeline
from app.services.rag.pipeline import RagPipeline
from app.services.storage.document_store import DocumentStore, GCSDocumentStore, LocalDocumentStore
from app.services.storage.vector_store import InMemoryVectorStore, VectorStore, VertexVectorSearchStore


@lru_cache
def get_ai_service() -> AIService:
    return build_ai_service(get_settings())


@lru_cache
def get_vector_store() -> VectorStore:
    settings = get_settings()
    if settings.gcp.use_live_vertex_ai:
        return VertexVectorSearchStore(
            project=settings.gcp.project_id,
            location=settings.gcp.location,
            index_id=settings.gcp.vector_index_id,
            index_endpoint_id=settings.gcp.vector_index_endpoint_id,
        )
    return InMemoryVectorStore()


@lru_cache
def get_document_store() -> DocumentStore:
    settings = get_settings()
    if settings.gcp.use_live_vertex_ai:
        return GCSDocumentStore(settings.gcp.documents_bucket)
    return LocalDocumentStore()


@lru_cache
def get_ingestion_pipeline() -> IngestionPipeline:
    settings = get_settings()
    return IngestionPipeline(
        document_store=get_document_store(),
        vector_store=get_vector_store(),
        ai_service=get_ai_service(),
        settings=settings,
    )


@lru_cache
def get_rag_pipeline() -> RagPipeline:
    settings = get_settings()
    return RagPipeline(ai_service=get_ai_service(), vector_store=get_vector_store(), settings=settings)


@lru_cache
def get_tool_registry() -> ToolRegistry:
    settings = get_settings()
    tools: list = [
        RagSearchTool(get_ai_service(), get_vector_store(), settings.retrieval),
        CalculatorTool(),
    ]
    if settings.mcp.enabled:
        tools.append(McpTextStatsTool(settings.mcp))
        tools.append(McpCurrentDatetimeTool(settings.mcp))
    return ToolRegistry(tools=tools)


@lru_cache
def get_agent() -> Agent:
    settings = get_settings()
    return Agent(get_ai_service(), get_tool_registry(), settings.agent)


def reset_caches_for_tests() -> None:
    """Test helper: clears all lru_cache singletons between test cases that
    need a fresh service graph (e.g. after monkeypatching settings)."""
    for fn in (
        get_ai_service,
        get_vector_store,
        get_document_store,
        get_ingestion_pipeline,
        get_rag_pipeline,
        get_tool_registry,
        get_agent,
    ):
        fn.cache_clear()  # type: ignore[attr-defined]
    get_settings.cache_clear()  # type: ignore[attr-defined]
