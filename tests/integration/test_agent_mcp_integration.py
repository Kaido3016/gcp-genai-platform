"""Confirms the bounded agent loop (app/services/agent/agent.py) actually
selects and uses an MCP-backed tool end to end, using the local mock AI
backend's tool-routing heuristic — the same pattern as the existing
calculator/rag_search agent tests in tests/integration/test_agent_loop.py.
Requires pydantic/FastAPI; not executed in the build sandbox (see
docs/FINAL_AUDIT.md). Run via `make test`."""

import sys

from app.core.config import AgentConfig, McpConfig
from app.schemas.agent import AgentStepKind, ToolName
from app.services.agent.agent import Agent
from app.services.agent.tools.base import ToolRegistry
from app.services.agent.tools.calculator_tool import CalculatorTool
from app.services.agent.tools.mcp_tool import McpCurrentDatetimeTool, McpTextStatsTool


def _agent(ai_service) -> Agent:
    mcp_config = McpConfig(
        enabled=True, server_command=(sys.executable, "-m", "app.mcp.server"), call_timeout_seconds=3.0
    )
    registry = ToolRegistry(
        tools=[CalculatorTool(), McpTextStatsTool(mcp_config), McpCurrentDatetimeTool(mcp_config)]
    )
    return Agent(ai_service, registry, AgentConfig(max_iterations=4, tool_timeout_seconds=5.0, max_tool_calls_per_turn=4))


def test_agent_uses_mcp_current_datetime_tool_for_date_query(ai_service):
    agent = _agent(ai_service)
    response = agent.run("What is today's date?")

    tool_call_steps = [s for s in response.steps if s.kind == AgentStepKind.TOOL_CALL]
    assert any(s.tool_call.tool == ToolName.MCP_CURRENT_DATETIME for s in tool_call_steps)

    tool_result_steps = [s for s in response.steps if s.kind == AgentStepKind.TOOL_RESULT]
    assert tool_result_steps
    assert tool_result_steps[0].tool_result.success is True
    assert "iso8601_utc" in tool_result_steps[0].tool_result.output

    assert response.stopped_reason == "final_answer"


def test_agent_still_prefers_calculator_for_math_over_mcp_tools(ai_service):
    """Confirms adding MCP tools didn't regress existing tool-routing
    priority — math queries still hit the calculator, not an MCP tool."""
    agent = _agent(ai_service)
    response = agent.run("What is 9 + 9?")
    tool_call_steps = [s for s in response.steps if s.kind == AgentStepKind.TOOL_CALL]
    assert any(s.tool_call.tool == ToolName.CALCULATOR for s in tool_call_steps)
    assert not any(s.tool_call.tool == ToolName.MCP_CURRENT_DATETIME for s in tool_call_steps)
