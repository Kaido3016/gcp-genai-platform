"""Abstract interfaces for the AI layer.

Phase 3: `Application AI Service -> Vertex AI Adapter -> Gemini`. Nothing
outside this package should import the Vertex AI SDK directly — every
caller (RAG pipeline, agent, API routes) depends on these interfaces only,
so the backend can be swapped (live Vertex AI vs. local/mock) via config
without touching business logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol

from pydantic import BaseModel


class GenerationResult(BaseModel):
    text: str
    model: str
    finish_reason: str = "stop"
    safety_blocked: bool = False
    input_tokens: int = 0
    output_tokens: int = 0


class ToolDeclaration(BaseModel):
    """Model-agnostic tool declaration passed to the generation call."""

    name: str
    description: str
    parameters_schema: dict  # JSON schema dict


class ToolInvocationRequest(BaseModel):
    name: str
    arguments: dict


class GenerationWithToolsResult(BaseModel):
    text: str | None = None
    tool_calls: list[ToolInvocationRequest] = []
    model: str
    finish_reason: str = "stop"
    input_tokens: int = 0
    output_tokens: int = 0


class EmbeddingResult(BaseModel):
    vectors: list[list[float]]
    model: str
    dimensionality: int


class GenerativeModelClient(Protocol):
    """Protocol implemented by any Gemini backend (live or mock)."""

    def generate(
        self,
        prompt: str,
        *,
        system_instruction: str | None = None,
        response_schema: dict | None = None,
    ) -> GenerationResult: ...

    def generate_with_tools(
        self,
        prompt: str,
        *,
        tools: list[ToolDeclaration],
        system_instruction: str | None = None,
        history: list[dict] | None = None,
    ) -> GenerationWithToolsResult: ...


class EmbeddingModelClient(Protocol):
    def embed(self, texts: list[str]) -> EmbeddingResult: ...


class AIService(ABC):
    """Application-facing facade. Business logic depends on this, never
    on a concrete Vertex/mock client directly."""

    @abstractmethod
    def generate_text(self, prompt: str, *, system_instruction: str | None = None) -> GenerationResult: ...

    @abstractmethod
    def generate_structured(self, prompt: str, *, response_schema: dict, system_instruction: str | None = None) -> GenerationResult: ...

    @abstractmethod
    def generate_with_tools(
        self,
        prompt: str,
        *,
        tools: list[ToolDeclaration],
        system_instruction: str | None = None,
        history: list[dict] | None = None,
    ) -> GenerationWithToolsResult: ...

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> EmbeddingResult: ...
