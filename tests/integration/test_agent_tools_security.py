"""Tests for Phase 7 agent safety controls: schema validation, timeouts,
authorization, and rejection of malicious/malformed tool inputs."""

import time

from pydantic import BaseModel

from app.schemas.agent import ToolName
from app.services.agent.tools.base import Tool, ToolRegistry
from app.services.agent.tools.calculator_tool import CalculatorTool


def test_calculator_rejects_code_injection_attempt(tool_registry):
    result = tool_registry.execute(
        ToolName.CALCULATOR,
        {"expression": "__import__('os').system('echo pwned')"},
        call_id="c1",
        context={},
        timeout_seconds=5,
    )
    assert result.success is False
    assert "Disallowed expression element" in result.error


def test_calculator_rejects_invalid_argument_schema(tool_registry):
    # 'expression' missing entirely -> Pydantic validation error, not a crash.
    result = tool_registry.execute(
        ToolName.CALCULATOR, {}, call_id="c2", context={}, timeout_seconds=5
    )
    assert result.success is False
    assert result.error is not None


def test_calculator_rejects_oversized_expression(tool_registry):
    huge_expr = "1+" * 500  # exceeds CalculatorArgs max_length=200
    result = tool_registry.execute(
        ToolName.CALCULATOR, {"expression": huge_expr}, call_id="c3", context={}, timeout_seconds=5
    )
    assert result.success is False


def test_rag_search_rejects_invalid_top_k(tool_registry):
    result = tool_registry.execute(
        ToolName.RAG_SEARCH,
        {"query": "test", "top_k": 999},  # exceeds le=20
        call_id="c4",
        context={"tenant_id": None},
        timeout_seconds=5,
    )
    assert result.success is False


def test_unknown_tool_returns_error_not_exception():
    registry = ToolRegistry(tools=[CalculatorTool()])
    result = registry.execute(
        ToolName.RAG_SEARCH, {"query": "x"}, call_id="c5", context={}, timeout_seconds=5
    )
    assert result.success is False
    assert "not registered" in result.error


class _SlowArgs(BaseModel):
    pass


class _SlowTool(Tool):
    name = ToolName.CALCULATOR  # reuse an existing enum value for the test
    description = "test tool that sleeps"
    allowed_for_all = True

    def run(self, args, *, context):
        time.sleep(2)
        return "should not get here"


def test_tool_execution_times_out():
    registry = ToolRegistry(tools=[_SlowTool()])
    result = registry.execute(
        ToolName.CALCULATOR, {"expression": "1+1"}, call_id="c6", context={}, timeout_seconds=0.1
    )
    assert result.success is False
    assert "timeout" in result.error.lower() or "exceeded" in result.error.lower()


class _PrivilegedTool(Tool):
    name = ToolName.CALCULATOR
    description = "privileged-only test tool"
    allowed_for_all = False

    def run(self, args, *, context):
        return "secret"


def test_tool_authorization_blocks_unprivileged_caller():
    registry = ToolRegistry(tools=[_PrivilegedTool()])
    result = registry.execute(
        ToolName.CALCULATOR,
        {"expression": "1+1"},
        call_id="c7",
        context={"is_privileged": False},
        timeout_seconds=5,
    )
    assert result.success is False
    assert "Not authorized" in result.error


def test_tool_authorization_allows_privileged_caller():
    registry = ToolRegistry(tools=[_PrivilegedTool()])
    result = registry.execute(
        ToolName.CALCULATOR,
        {"expression": "1+1"},
        call_id="c8",
        context={"is_privileged": True},
        timeout_seconds=5,
    )
    assert result.success is True
    assert result.output == "secret"
