"""Explicit exception hierarchy.

Phase 15 requires avoiding broad exception handling that hides errors.
Every failure mode that the API/agent/RAG layers need to distinguish
gets its own exception class here instead of bare `except Exception`.
"""

from __future__ import annotations


class PlatformError(Exception):
    """Base class for all application-raised errors."""


# --- Ingestion / document handling -----------------------------------------


class DocumentValidationError(PlatformError):
    """Raised when an uploaded document fails validation (type, size, content)."""


class DocumentProcessingError(PlatformError):
    """Raised when text extraction or chunking fails for a stored document."""


# --- AI / Vertex adapter -----------------------------------------------------


class ModelGenerationError(PlatformError):
    """Raised when the generation model fails after exhausting retries."""


class ModelTimeoutError(ModelGenerationError):
    """Raised when a model call exceeds the configured timeout."""


class ModelSafetyBlockError(ModelGenerationError):
    """Raised when a response is blocked by safety filtering."""


class StructuredOutputValidationError(PlatformError):
    """Raised when a model's structured output fails schema validation."""


class EmbeddingError(PlatformError):
    """Raised when embedding generation fails."""


# --- Retrieval / vector store -------------------------------------------------


class VectorStoreError(PlatformError):
    """Raised when the vector store backend fails to index or query."""


class RetrievalError(PlatformError):
    """Raised when the retrieval step cannot produce usable context."""


# --- Agent --------------------------------------------------------------------


class AgentError(PlatformError):
    """Base class for agent-loop failures."""


class MaxIterationsExceededError(AgentError):
    """Raised when the agent hits its iteration cap without a final answer."""


class ToolNotFoundError(AgentError):
    """Raised when the model requests a tool that isn't registered."""


class ToolInputValidationError(AgentError):
    """Raised when tool arguments fail schema validation before execution."""


class ToolExecutionError(AgentError):
    """Raised when a tool raises during execution."""


class ToolTimeoutError(ToolExecutionError):
    """Raised when a tool exceeds its configured timeout."""


class ToolAuthorizationError(AgentError):
    """Raised when a requested tool is not authorized for the current context."""


# --- Security -------------------------------------------------------------------


class PromptInjectionSuspectedError(PlatformError):
    """Raised when input heuristics flag likely prompt-injection content."""


class UnauthorizedError(PlatformError):
    """Raised on authentication/authorization failure."""
