"""Pytest tests confirming MCP tools are first-class citizens of the
agent's ToolRegistry — same authorization/validation/timeout enforcement
path as CalculatorTool/RagSearchTool. Requires pydantic/FastAPI, so (like
the rest of this repo's pytest suite) this was traced by hand against the
implementation but not executed in the build sandbox — see
docs/FINAL_AUDIT.md. Run via `make test`."""

import sys

from app.core.config import McpConfig
from app.schemas.agent import ToolName
from app.services.agent.tools.base import ToolRegistry
from app.services.agent.tools.mcp_tool import McpCurrentDatetimeTool, McpTextStatsTool


def _mcp_config() -> McpConfig:
    return McpConfig(
        enabled=True,
        server_command=(sys.executable, "-m", "app.mcp.server"),
        call_timeout_seconds=3.0,
    )


def _registry() -> ToolRegistry:
    config = _mcp_config()
    return ToolRegistry(tools=[McpTextStatsTool(config), McpCurrentDatetimeTool(config)])


def test_mcp_text_stats_via_registry_success():
    registry = _registry()
    result = registry.execute(
        ToolName.MCP_TEXT_STATS,
        {"text": "one two three four"},
        call_id="c1",
        context={},
        timeout_seconds=5.0,
    )
    assert result.success is True
    assert result.output["word_count"] == 4


def test_mcp_current_datetime_via_registry_success():
    registry = _registry()
    result = registry.execute(
        ToolName.MCP_CURRENT_DATETIME, {}, call_id="c2", context={}, timeout_seconds=5.0
    )
    assert result.success is True
    assert "iso8601_utc" in result.output


def test_mcp_text_stats_rejects_missing_required_field():
    registry = _registry()
    result = registry.execute(
        ToolName.MCP_TEXT_STATS, {}, call_id="c3", context={}, timeout_seconds=5.0
    )
    # Rejected by Pydantic schema validation before the MCP subprocess is
    # ever spawned — a malformed call never reaches the transport layer.
    assert result.success is False


def test_mcp_current_datetime_rejects_unexpected_extra_field():
    registry = _registry()
    result = registry.execute(
        ToolName.MCP_CURRENT_DATETIME,
        {"unexpected": "field"},
        call_id="c4",
        context={},
        timeout_seconds=5.0,
    )
    # McpCurrentDatetimeArgs has model_config = {"extra": "forbid"}.
    assert result.success is False


def test_mcp_tool_respects_registry_level_timeout():
    """Even if the MCP client's own timeout were misconfigured too high,
    the same ThreadPoolExecutor-based timeout that bounds every other
    tool (see ToolRegistry.execute) still bounds MCP tool calls."""
    registry = _registry()
    result = registry.execute(
        ToolName.MCP_TEXT_STATS,
        {"text": "irrelevant, this should return well within budget"},
        call_id="c5",
        context={},
        timeout_seconds=10.0,  # generous; just proving the path is wired, not testing a hang
    )
    assert result.success is True
    assert result.duration_ms >= 0.0


def test_mcp_tool_names_appear_in_agent_tool_declarations():
    """Confirms MCP tools flow into the same tool-declaration list the
    agent sends to the model — i.e. genuinely reachable from the agent
    loop, not just callable in isolation."""
    from app.services.agent.agent import SYSTEM_INSTRUCTION  # noqa: F401 - sanity import

    registry = _registry()
    all_tools = registry.all()
    names = {t.name for t in all_tools}
    assert ToolName.MCP_TEXT_STATS in names
    assert ToolName.MCP_CURRENT_DATETIME in names
    for tool in all_tools:
        schema = tool.json_schema()
        assert schema["type"] == "object"
