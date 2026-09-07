"""Concrete AIService: the only thing the rest of the app depends on.

RAG pipeline, agent, and API routes call `AIService`, never a Vertex or
mock client directly (Phase 3). Retry/backoff and timeout policy live
here in one place instead of being duplicated at every call site.
"""

from __future__ import annotations

import json
import logging
import time

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    EmbeddingError,
    ModelGenerationError,
    StructuredOutputValidationError,
)
from app.core.logging import get_logger, log_event
from app.services.ai.base import (
    AIService,
    EmbeddingModelClient,
    EmbeddingResult,
    GenerationResult,
    GenerationWithToolsResult,
    GenerativeModelClient,
    ToolDeclaration,
)
from app.services.ai.retry import call_with_retry

logger = get_logger(__name__)


class DefaultAIService(AIService):
    def __init__(
        self,
        generative_client: GenerativeModelClient,
        embedding_client: EmbeddingModelClient,
        settings: Settings,
    ):
        self._gen = generative_client
        self._embed_client = embedding_client
        self._settings = settings

    def generate_text(
        self, prompt: str, *, system_instruction: str | None = None
    ) -> GenerationResult:
        gen_cfg = self._settings.generation
        start = time.perf_counter()
        try:
            result = call_with_retry(
                lambda: self._gen.generate(prompt, system_instruction=system_instruction),
                max_retries=gen_cfg.max_retries,
                backoff_base_seconds=gen_cfg.retry_backoff_base_seconds,
                retryable_exceptions=(ModelGenerationError,),
            )
        except Exception as exc:
            log_event(logger, logging.ERROR, "generation_failed", error=str(exc))
            raise
        log_event(
            logger,
            logging.INFO,
            "generation_succeeded",
            model=result.model,
            duration_ms=round((time.perf_counter() - start) * 1000, 1),
            output_tokens=result.output_tokens,
        )
        return result

    def generate_structured(
        self,
        prompt: str,
        *,
        response_schema: dict,
        system_instruction: str | None = None,
    ) -> GenerationResult:
        gen_cfg = self._settings.generation
        annotated_prompt = (
            prompt
            + "\n\nRespond ONLY with JSON matching this schema, no prose: "
            + json.dumps(response_schema)
        )
        try:
            result = call_with_retry(
                lambda: self._gen.generate(
                    annotated_prompt,
                    system_instruction=system_instruction,
                    response_schema=response_schema,
                ),
                max_retries=gen_cfg.max_retries,
                backoff_base_seconds=gen_cfg.retry_backoff_base_seconds,
                retryable_exceptions=(ModelGenerationError,),
            )
        except Exception as exc:
            log_event(logger, logging.ERROR, "structured_generation_failed", error=str(exc))
            raise
        self._validate_json_against_schema(result.text, response_schema)
        return result

    def generate_with_tools(
        self,
        prompt: str,
        *,
        tools: list[ToolDeclaration],
        system_instruction: str | None = None,
        history: list[dict] | None = None,
    ) -> GenerationWithToolsResult:
        gen_cfg = self._settings.generation
        return call_with_retry(
            lambda: self._gen.generate_with_tools(
                prompt, tools=tools, system_instruction=system_instruction, history=history
            ),
            max_retries=gen_cfg.max_retries,
            backoff_base_seconds=gen_cfg.retry_backoff_base_seconds,
            retryable_exceptions=(ModelGenerationError,),
        )

    def embed_texts(self, texts: list[str]) -> EmbeddingResult:
        embed_cfg = self._settings.embedding
        try:
            return call_with_retry(
                lambda: self._embed_client.embed(texts),
                max_retries=embed_cfg.max_retries,
                backoff_base_seconds=1.0,
                retryable_exceptions=(EmbeddingError,),
            )
        except Exception as exc:
            log_event(
                logger, logging.ERROR, "embedding_failed", error=str(exc), text_count=len(texts)
            )
            raise

    @staticmethod
    def _validate_json_against_schema(text: str, schema: dict) -> None:
        """Minimal, dependency-free structural validation. We never trust
        an LLM response as valid application data without checking it
        (Phase 8) — required fields, types, and enum values are enforced.
        """
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise StructuredOutputValidationError(
                f"Model output was not valid JSON: {exc}"
            ) from exc

        if not isinstance(data, dict):
            raise StructuredOutputValidationError("Model output JSON must be an object.")

        required = schema.get("required", [])
        for field in required:
            if field not in data:
                raise StructuredOutputValidationError(f"Missing required field: {field}")

        props = schema.get("properties", {})
        type_map: dict[str, type | tuple[type, ...]] = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
        }
        for field, value in data.items():
            prop = props.get(field)
            if not prop:
                continue
            expected = type_map.get(prop.get("type", ""))
            if expected and not isinstance(value, expected):
                raise StructuredOutputValidationError(
                    f"Field '{field}' expected type {prop.get('type')}, got {type(value).__name__}"
                )
            if "enum" in prop and value not in prop["enum"]:
                raise StructuredOutputValidationError(
                    f"Field '{field}' value '{value}' not in allowed enum {prop['enum']}"
                )


def build_ai_service(settings: Settings | None = None) -> DefaultAIService:
    """Factory: chooses the live Vertex backend or the local mock backend
    based on settings.gcp.use_live_vertex_ai. This is the one place that
    decides which backend gets wired in."""
    settings = settings or get_settings()

    if settings.gcp.use_live_vertex_ai:
        from app.services.ai.vertex_backend import VertexEmbeddingClient, VertexGenerativeClient

        gen_client: GenerativeModelClient = VertexGenerativeClient(
            project=settings.gcp.project_id,
            location=settings.gcp.location,
            model_name=settings.generation.model_name,
            temperature=settings.generation.temperature,
            top_p=settings.generation.top_p,
            max_output_tokens=settings.generation.max_output_tokens,
            safety_settings={
                "HARASSMENT": settings.safety.harassment_threshold,
                "HATE_SPEECH": settings.safety.hate_speech_threshold,
                "SEXUALLY_EXPLICIT": settings.safety.sexually_explicit_threshold,
                "DANGEROUS_CONTENT": settings.safety.dangerous_content_threshold,
            },
        )
        embed_client: EmbeddingModelClient = VertexEmbeddingClient(
            project=settings.gcp.project_id,
            location=settings.gcp.location,
            model_name=settings.embedding.model_name,
            output_dimensionality=settings.embedding.output_dimensionality,
        )
    else:
        from app.services.ai.local_backend import LocalEmbeddingClient, LocalGenerativeClient

        gen_client = LocalGenerativeClient(model_name=settings.generation.model_name)
        embed_client = LocalEmbeddingClient(
            model_name=settings.embedding.model_name,
            dimensionality=settings.embedding.output_dimensionality,
        )

    return DefaultAIService(gen_client, embed_client, settings)
