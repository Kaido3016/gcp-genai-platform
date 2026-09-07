"""Live Vertex AI / Gemini backend.

This is real, runnable code against the `google-genai` SDK — but it has
NOT been executed against a live GCP project in this environment (no
network access / credentials here). Wire it up with a real project and
`GCP_USE_LIVE_VERTEX_AI=true` to actually exercise it; see
docs/DEPLOYMENT.md for setup steps.

Imports are deferred into __init__ so the rest of the application can be
imported and unit-tested (with the local backend) even when the
`google-genai` package or credentials are unavailable.
"""

from __future__ import annotations

from typing import Any

from app.services.ai.base import (
    EmbeddingResult,
    GenerationResult,
    GenerationWithToolsResult,
    ToolDeclaration,
    ToolInvocationRequest,
)
from app.core.exceptions import EmbeddingError, ModelGenerationError, ModelSafetyBlockError


class VertexGenerativeClient:
    def __init__(
        self,
        *,
        project: str,
        location: str,
        model_name: str,
        temperature: float,
        top_p: float,
        max_output_tokens: int,
        safety_settings: dict[str, str],
    ):
        try:
            from google import genai  # type: ignore
        except ImportError as exc:  # pragma: no cover - exercised only with SDK installed
            raise ModelGenerationError(
                "google-genai SDK is not installed. Run `pip install google-genai` "
                "and configure GCP credentials to use the live backend."
            ) from exc

        self._genai = genai
        self._client = genai.Client(vertexai=True, project=project, location=location)
        self.model_name = model_name
        self.temperature = temperature
        self.top_p = top_p
        self.max_output_tokens = max_output_tokens
        self.safety_settings = safety_settings

    def generate(
        self,
        prompt: str,
        *,
        system_instruction: str | None = None,
        response_schema: dict | None = None,
    ) -> GenerationResult:
        config: dict[str, Any] = {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_output_tokens": self.max_output_tokens,
        }
        if system_instruction:
            config["system_instruction"] = system_instruction
        if response_schema:
            config["response_mime_type"] = "application/json"
            config["response_schema"] = response_schema

        try:
            response = self._client.models.generate_content(
                model=self.model_name, contents=prompt, config=config
            )
        except Exception as exc:  # SDK raises various transient/API errors
            raise ModelGenerationError(f"Gemini generation failed: {exc}") from exc

        if getattr(response, "prompt_feedback", None) and getattr(
            response.prompt_feedback, "block_reason", None
        ):
            raise ModelSafetyBlockError(str(response.prompt_feedback.block_reason))

        usage = getattr(response, "usage_metadata", None)
        return GenerationResult(
            text=response.text or "",
            model=self.model_name,
            input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
            output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
        )

    def generate_with_tools(
        self,
        prompt: str,
        *,
        tools: list[ToolDeclaration],
        system_instruction: str | None = None,
        history: list[dict] | None = None,
    ) -> GenerationWithToolsResult:
        function_declarations = [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters_schema,
            }
            for t in tools
        ]
        config: dict[str, Any] = {"tools": [{"function_declarations": function_declarations}]}
        if system_instruction:
            config["system_instruction"] = system_instruction

        try:
            response = self._client.models.generate_content(
                model=self.model_name, contents=prompt, config=config
            )
        except Exception as exc:
            raise ModelGenerationError(f"Gemini tool-call generation failed: {exc}") from exc

        candidate = response.candidates[0] if response.candidates else None
        tool_calls: list[ToolInvocationRequest] = []
        text: str | None = None
        if candidate and candidate.content and candidate.content.parts:
            for part in candidate.content.parts:
                fc = getattr(part, "function_call", None)
                if fc:
                    tool_calls.append(
                        ToolInvocationRequest(name=fc.name, arguments=dict(fc.args or {}))
                    )
                elif getattr(part, "text", None):
                    text = (text or "") + part.text

        usage = getattr(response, "usage_metadata", None)
        return GenerationWithToolsResult(
            text=text,
            tool_calls=tool_calls,
            model=self.model_name,
            input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
            output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
        )


class VertexEmbeddingClient:
    def __init__(self, *, project: str, location: str, model_name: str, output_dimensionality: int):
        try:
            from google import genai  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise EmbeddingError(
                "google-genai SDK is not installed. Run `pip install google-genai`."
            ) from exc

        self._client = genai.Client(vertexai=True, project=project, location=location)
        self.model_name = model_name
        self.output_dimensionality = output_dimensionality

    def embed(self, texts: list[str]) -> EmbeddingResult:
        try:
            response = self._client.models.embed_content(
                model=self.model_name,
                contents=texts,
                config={"output_dimensionality": self.output_dimensionality},
            )
        except Exception as exc:
            raise EmbeddingError(f"Embedding generation failed: {exc}") from exc

        vectors = [list(e.values) for e in response.embeddings]
        return EmbeddingResult(
            vectors=vectors, model=self.model_name, dimensionality=self.output_dimensionality
        )
