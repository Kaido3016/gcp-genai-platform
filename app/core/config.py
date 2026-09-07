"""Centralized, environment-driven configuration.

Phase 3 requirement: no hardcoded model names, temperature, retrieval
parameters, timeouts, or retry configuration anywhere else in the codebase.
Every tunable lives here and is overridable via environment variables
(see .env.example).
"""

from __future__ import annotations

import sys
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class GenerationConfig(BaseSettings):
    """Tunables for Gemini text generation."""

    model_config = SettingsConfigDict(env_prefix="GEN_")

    model_name: str = Field(
        default="gemini-2.0-flash-001",
        description=(
            "Chat/generation model. Flash is the default because the "
            "flagship use case (grounded RAG answers, agent tool reasoning) "
            "is latency- and cost-sensitive; swap to a Pro-tier model via "
            "env var for tasks that need deeper reasoning. See "
            "docs/ARCHITECTURE.md#model-selection for the full rationale."
        ),
    )
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    top_p: float = Field(default=0.95, ge=0.0, le=1.0)
    max_output_tokens: int = Field(default=1024, ge=1, le=8192)
    timeout_seconds: float = Field(default=30.0, gt=0)
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_backoff_base_seconds: float = Field(default=1.0, gt=0)


class EmbeddingConfig(BaseSettings):
    """Tunables for the embedding model used across ingestion and retrieval."""

    model_config = SettingsConfigDict(env_prefix="EMBED_")

    model_name: str = Field(default="text-embedding-005")
    output_dimensionality: int = Field(default=768, ge=1)
    batch_size: int = Field(default=16, ge=1, le=250)
    timeout_seconds: float = Field(default=15.0, gt=0)
    max_retries: int = Field(default=3, ge=0, le=10)


class RetrievalConfig(BaseSettings):
    """Tunables for the RAG retrieval step."""

    model_config = SettingsConfigDict(env_prefix="RETRIEVAL_")

    top_k: int = Field(default=8, ge=1, le=50)
    similarity_threshold: float = Field(
        default=0.15,
        ge=0.0,
        le=1.0,
        description=(
            "Cosine similarity floor; chunks below this are dropped. This "
            "default (0.15) is calibrated for the local mock embedding "
            "backend's score distribution (see docs/RAG_DESIGN.md and "
            "AI_EVALUATION.md), which produces much lower and less "
            "separated cosine scores than a real trained embedding model. "
            "Re-tune this against Vertex AI text-embedding-005 scores "
            "before relying on it in a live deployment — do not assume "
            "this value transfers."
        ),
    )
    max_context_chunks: int = Field(default=5, ge=1, le=20)
    chunk_size_tokens: int = Field(default=400, ge=50, le=2000)
    chunk_overlap_tokens: int = Field(default=60, ge=0, le=500)
    dedupe_similarity_threshold: float = Field(default=0.97, ge=0.0, le=1.0)


class AgentConfig(BaseSettings):
    """Tunables and safety limits for the agentic workflow (Phase 7)."""

    model_config = SettingsConfigDict(env_prefix="AGENT_")

    max_iterations: int = Field(
        default=6, ge=1, le=25, description="Hard stop to prevent infinite loops."
    )
    tool_timeout_seconds: float = Field(default=10.0, gt=0)
    max_tool_calls_per_turn: int = Field(default=8, ge=1, le=50)


class SafetyConfig(BaseSettings):
    """Gemini safety-setting thresholds. Kept explicit and documented rather
    than left at SDK defaults, since a reviewer will ask about this."""

    model_config = SettingsConfigDict(env_prefix="SAFETY_")

    harassment_threshold: str = Field(default="BLOCK_MEDIUM_AND_ABOVE")
    hate_speech_threshold: str = Field(default="BLOCK_MEDIUM_AND_ABOVE")
    sexually_explicit_threshold: str = Field(default="BLOCK_MEDIUM_AND_ABOVE")
    dangerous_content_threshold: str = Field(default="BLOCK_MEDIUM_AND_ABOVE")


class GCPConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GCP_")

    project_id: str = Field(default="local-dev-project")
    location: str = Field(default="us-central1")
    documents_bucket: str = Field(default="genai-platform-documents")
    vector_index_id: str = Field(default="")
    vector_index_endpoint_id: str = Field(default="")
    use_live_vertex_ai: bool = Field(
        default=False,
        description=(
            "When False (default for local dev / CI / this portfolio "
            "environment), the app uses the in-memory/mocked AI and vector "
            "store backends so it runs without GCP credentials or network "
            "access. Set True only when running against a real GCP project."
        ),
    )


class McpConfig(BaseSettings):
    """Config for the MCP (Model Context Protocol) integration.

    Kept intentionally minimal — one server, spawned as a local
    subprocess over stdio, matching docs/MCP.md's scope. See
    app/services/agent/tools/mcp_tool.py for how these are used.
    """

    model_config = SettingsConfigDict(env_prefix="MCP_")

    enabled: bool = Field(
        default=True,
        description="If False, MCP tools are not registered with the agent's tool registry at all.",
    )
    server_command: tuple[str, ...] = Field(
        default=(sys.executable, "-m", "app.mcp.server"),
        description="Command used to spawn the MCP server subprocess.",
    )
    call_timeout_seconds: float = Field(
        default=5.0,
        gt=0,
        description="Client-side timeout per MCP call, enforced independently of the server's own timeout.",
    )


class UploadConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="UPLOAD_")

    max_file_size_mb: int = Field(default=20, ge=1, le=200)
    allowed_extensions: tuple[str, ...] = (".pdf", ".txt", ".md", ".docx")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")
    request_id_header: str = Field(default="X-Request-ID")

    gcp: GCPConfig = Field(default_factory=GCPConfig)
    generation: GenerationConfig = Field(default_factory=GenerationConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    upload: UploadConfig = Field(default_factory=UploadConfig)
    mcp: McpConfig = Field(default_factory=McpConfig)


@lru_cache
def get_settings() -> Settings:
    """Settings are cached: read once per process, override via env/.env."""
    return Settings()
