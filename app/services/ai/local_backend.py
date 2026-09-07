"""Deterministic local backend implementing the same protocols as the live
Vertex AI client (app/services/ai/vertex_backend.py).

Used when settings.gcp.use_live_vertex_ai is False — which is the default,
since this portfolio environment has no network access or GCP credentials.
It lets the entire application, RAG pipeline, and agent be developed,
unit-tested, and demoed end-to-end without live billing or credentials,
while keeping the exact same interface the live backend implements — so
switching to real Vertex AI is a one-line config change, not a rewrite.

This is intentionally simple (hashing-based embeddings, template-based
generation) — it is a development/test double, not a claim of model quality.
"""

from __future__ import annotations

import hashlib
import json
import re

from app.services.ai.base import (
    EmbeddingResult,
    GenerationResult,
    GenerationWithToolsResult,
    ToolDeclaration,
    ToolInvocationRequest,
)


def _hash_embed(text: str, dim: int) -> list[float]:
    """Deterministic pseudo-embedding: stable across runs, good enough to
    exercise cosine-similarity ranking logic in tests without a real model."""
    vec = [0.0] * dim
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    for tok in tokens:
        h = int(hashlib.sha256(tok.encode()).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h >> 1) % 2 == 0 else -1.0
        vec[idx] += sign
    norm = sum(v * v for v in vec) ** 0.5
    if norm == 0:
        return vec
    return [v / norm for v in vec]


class LocalEmbeddingClient:
    def __init__(self, model_name: str, dimensionality: int):
        self.model_name = model_name
        self.dimensionality = dimensionality

    def embed(self, texts: list[str]) -> EmbeddingResult:
        vectors = [_hash_embed(t, self.dimensionality) for t in texts]
        return EmbeddingResult(
            vectors=vectors, model=self.model_name, dimensionality=self.dimensionality
        )


class LocalGenerativeClient:
    """Template-based generation good enough for wiring/testing the RAG and
    agent control flow deterministically, without calling a real model."""

    def __init__(self, model_name: str):
        self.model_name = model_name

    def generate(
        self,
        prompt: str,
        *,
        system_instruction: str | None = None,
        response_schema: dict | None = None,
    ) -> GenerationResult:
        if response_schema is not None:
            text = self._fake_structured_response(response_schema)
        else:
            text = self._fake_grounded_answer(prompt)
        return GenerationResult(
            text=text,
            model=self.model_name,
            input_tokens=len(prompt.split()),
            output_tokens=len(text.split()),
        )

    def generate_with_tools(
        self,
        prompt: str,
        *,
        tools: list[ToolDeclaration],
        system_instruction: str | None = None,
        history: list[dict] | None = None,
    ) -> GenerationWithToolsResult:
        history = history or []
        already_called = {
            h.get("tool") for h in history if h.get("role") == "tool_result"
        }
        tool_calls: list[ToolInvocationRequest] = []

        lower = prompt.lower()
        available = [t.name for t in tools]

        if "calculator" in available and self._looks_like_math(lower) and "calculator" not in already_called:
            expr = self._extract_expression(prompt)
            if expr:
                tool_calls.append(ToolInvocationRequest(name="calculator", arguments={"expression": expr}))
        elif (
            "mcp_current_datetime" in available
            and self._looks_like_datetime_query(lower)
            and "mcp_current_datetime" not in already_called
        ):
            tool_calls.append(ToolInvocationRequest(name="mcp_current_datetime", arguments={}))
        elif "rag_search" in available and "rag_search" not in already_called:
            tool_calls.append(
                ToolInvocationRequest(name="rag_search", arguments={"query": prompt, "top_k": 5})
            )

        if tool_calls:
            return GenerationWithToolsResult(
                text=None,
                tool_calls=tool_calls,
                model=self.model_name,
                input_tokens=len(prompt.split()),
                output_tokens=0,
            )

        final_text = self._compose_final_answer(prompt, history)
        return GenerationWithToolsResult(
            text=final_text,
            tool_calls=[],
            model=self.model_name,
            input_tokens=len(prompt.split()),
            output_tokens=len(final_text.split()),
        )

    @staticmethod
    def _looks_like_math(text: str) -> bool:
        return bool(re.search(r"\d+\s*[\+\-\*/]\s*\d+", text))

    @staticmethod
    def _looks_like_datetime_query(text: str) -> bool:
        return bool(re.search(r"\b(today|current date|current time|what time|what.s the date|right now)\b", text))

    @staticmethod
    def _extract_expression(text: str) -> str | None:
        match = re.search(r"[\d\.\s\+\-\*/\(\)]{3,}", text)
        return match.group(0).strip() if match else None

    @staticmethod
    def _fake_grounded_answer(prompt: str) -> str:
        return (
            "Based on the retrieved context, here is a grounded answer. "
            "(local mock backend — replace with live Gemini output by "
            "setting GCP_USE_LIVE_VERTEX_AI=true and valid credentials.)"
        )

    @staticmethod
    def _fake_structured_response(schema: dict) -> str:
        required = schema.get("required", list(schema.get("properties", {}).keys()))
        props = schema.get("properties", {})
        obj = {}
        for key in required:
            prop = props.get(key, {})
            if "enum" in prop and prop["enum"]:
                obj[key] = prop["enum"][0]
                continue
            ptype = prop.get("type", "string")
            if ptype == "string":
                obj[key] = "mock_value"
            elif ptype == "integer":
                obj[key] = 0
            elif ptype == "number":
                obj[key] = 0.0
            elif ptype == "boolean":
                obj[key] = False
            elif ptype == "array":
                obj[key] = []
            else:
                obj[key] = None
        return json.dumps(obj)

    @staticmethod
    def _compose_final_answer(prompt: str, history: list[dict]) -> str:
        tool_outputs = [h for h in history if h.get("role") == "tool_result"]
        if tool_outputs:
            last = tool_outputs[-1]
            return f"Tool result: {last.get('output')}. This answers: {prompt[:200]}"
        return "I could not determine a tool to use for this request."
