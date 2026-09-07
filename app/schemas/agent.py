"""Agent request/response and tool-call schemas.

Phase 7/8 requirement: strict tool schemas, validated inputs, no arbitrary
code execution, bounded iterations — enforced by these types plus the
agent loop in app/services/agent/agent.py.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolName(StrEnum):
    RAG_SEARCH = "rag_search"
    CALCULATOR = "calculator"
    MCP_TEXT_STATS = "mcp_text_stats"
    MCP_CURRENT_DATETIME = "mcp_current_datetime"


class ToolCall(BaseModel):
    tool: ToolName
    arguments: dict[str, Any]
    call_id: str


class ToolResult(BaseModel):
    call_id: str
    tool: ToolName
    success: bool
    output: Any = None
    error: str | None = None
    duration_ms: float = 0.0


class AgentStepKind(StrEnum):
    THOUGHT = "thought"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    FINAL_ANSWER = "final_answer"


class AgentStep(BaseModel):
    kind: AgentStepKind
    content: str
    tool_call: ToolCall | None = None
    tool_result: ToolResult | None = None


class AgentRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    tenant_id: str | None = None


class AgentResponse(BaseModel):
    answer: str
    steps: list[AgentStep]
    iterations_used: int
    stopped_reason: Literal["final_answer", "max_iterations", "error"]
    model_used: str
    latency_ms: float


class RagSearchArgs(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)


class CalculatorArgs(BaseModel):
    expression: str = Field(
        min_length=1,
        max_length=200,
        description="A restricted arithmetic expression, e.g. '(3 + 4) * 2'.",
    )


class McpTextStatsArgs(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)


class McpCurrentDatetimeArgs(BaseModel):
    """No parameters; unexpected fields are rejected."""

    model_config = {"extra": "forbid"}


TOOL_ARG_SCHEMAS: dict[ToolName, type[BaseModel]] = {
    ToolName.RAG_SEARCH: RagSearchArgs,
    ToolName.CALCULATOR: CalculatorArgs,
    ToolName.MCP_TEXT_STATS: McpTextStatsArgs,
    ToolName.MCP_CURRENT_DATETIME: McpCurrentDatetimeArgs,
}
