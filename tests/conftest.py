from __future__ import annotations

import pytest

from app.core.config import Settings
from app.services.agent.agent import Agent
from app.services.agent.tools.base import ToolRegistry
from app.services.agent.tools.calculator_tool import CalculatorTool
from app.services.agent.tools.rag_tool import RagSearchTool
from app.services.ai.local_backend import LocalEmbeddingClient, LocalGenerativeClient
from app.services.ai.service import DefaultAIService
from app.services.rag.ingestion import IngestionPipeline
from app.services.rag.pipeline import RagPipeline
from app.services.storage.document_store import LocalDocumentStore
from app.services.storage.vector_store import InMemoryVectorStore


@pytest.fixture
def settings(tmp_path) -> Settings:
    s = Settings()
    s.gcp.use_live_vertex_ai = False
    return s


@pytest.fixture
def ai_service(settings) -> DefaultAIService:
    gen = LocalGenerativeClient(model_name=settings.generation.model_name)
    embed = LocalEmbeddingClient(
        model_name=settings.embedding.model_name,
        dimensionality=settings.embedding.output_dimensionality,
    )
    return DefaultAIService(gen, embed, settings)


@pytest.fixture
def vector_store() -> InMemoryVectorStore:
    return InMemoryVectorStore()


@pytest.fixture
def document_store(tmp_path) -> LocalDocumentStore:
    return LocalDocumentStore(base_dir=str(tmp_path))


@pytest.fixture
def ingestion_pipeline(document_store, vector_store, ai_service, settings) -> IngestionPipeline:
    return IngestionPipeline(
        document_store=document_store,
        vector_store=vector_store,
        ai_service=ai_service,
        settings=settings,
    )


@pytest.fixture
def rag_pipeline(ai_service, vector_store, settings) -> RagPipeline:
    return RagPipeline(ai_service=ai_service, vector_store=vector_store, settings=settings)


@pytest.fixture
def tool_registry(ai_service, vector_store, settings) -> ToolRegistry:
    return ToolRegistry(
        tools=[
            RagSearchTool(ai_service, vector_store, settings.retrieval),
            CalculatorTool(),
        ]
    )


@pytest.fixture
def agent(ai_service, tool_registry, settings) -> Agent:
    return Agent(ai_service, tool_registry, settings.agent)
