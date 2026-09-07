"""Wraps the MCP client (app/mcp/client.py) as agent-framework `Tool`s.

This is the layer that actually connects MCP to the Agentic AI flow: these
classes are registered in the same `ToolRegistry` as `CalculatorTool` and
`RagSearchTool` (see app/dependencies.py), so the agent loop
(app/services/agent/agent.py) calls them exactly the same way — it has no
idea, and doesn't need to, that these particular tools talk to a
subprocess over JSON-RPC instead of running in-process.

Design tradeoff, stated plainly: each call spawns a fresh MCP server
subprocess rather than keeping one long-lived process per tool. This is
simpler and avoids shared-mutable-state bugs across concurrent agent
tool calls (MCPClient is documented as not safe for concurrent calls on
one instance), at the cost of subprocess-startup latency (double-digit
milliseconds) on every call. Fine for a portfolio-scale demo; a real
deployment handling meaningful QPS would want a persistent server process
or a pool of them — noted here rather than silently accepted.

Untrusted content handling: the dict returned by `MCPClient.call_tool`
is treated purely as data. It is JSON-serializable primitives only (the
server's handlers return plain dicts of str/int/float/bool — see
app/mcp/server.py), never executed, never used to build a shell command,
and only reaches the model as inert text inside the next prompt — the
same trust boundary already applied to RagSearchTool's retrieved chunk
text and CalculatorTool's numeric result.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.core.config import McpConfig
from app.core.exceptions import ToolExecutionError
from app.mcp.client import MCPClient, MCPProtocolError
from app.schemas.agent import McpCurrentDatetimeArgs, McpTextStatsArgs, ToolName
from app.services.agent.tools.base import Tool


class _McpBackedTool(Tool):
    """Shared plumbing for MCP-backed tools: spawn a client, call the
    named MCP tool, translate transport errors into ToolExecutionError
    (never let a raw subprocess/JSON error escape to the agent loop),
    always close the subprocess."""

    mcp_tool_name: str

    def __init__(self, mcp_config: McpConfig):
        self._config = mcp_config

    def _call_mcp(self, arguments: dict[str, Any]) -> Any:
        try:
            with MCPClient(
                list(self._config.server_command), call_timeout_seconds=self._config.call_timeout_seconds
            ) as client:
                return client.call_tool(self.mcp_tool_name, arguments)
        except MCPProtocolError as exc:
            # A malformed/unexpected wire message from the server is a
            # transport-integrity failure, not a normal tool error — still
            # converted to our standard exception type rather than
            # propagating a raw protocol exception into the agent loop.
            raise ToolExecutionError(f"MCP protocol error calling '{self.mcp_tool_name}': {exc}") from exc


class McpTextStatsTool(_McpBackedTool):
    name = ToolName.MCP_TEXT_STATS
    mcp_tool_name = "text_stats"
    description = (
        "Compute word/character/sentence counts and an estimated reading "
        "time for a piece of text, via an external MCP server. Use this "
        "for questions like 'how long is this' or 'how many words'."
    )
    allowed_for_all = True

    def run(self, args: BaseModel, *, context: dict[str, Any]) -> Any:
        assert isinstance(args, McpTextStatsArgs)
        return self._call_mcp({"text": args.text})


class McpCurrentDatetimeTool(_McpBackedTool):
    name = ToolName.MCP_CURRENT_DATETIME
    mcp_tool_name = "current_datetime"
    description = (
        "Get the current UTC date and time via an external MCP server. "
        "Use this for any question involving 'today', 'now', or relative dates."
    )
    allowed_for_all = True

    def run(self, args: BaseModel, *, context: dict[str, Any]) -> Any:
        assert isinstance(args, McpCurrentDatetimeArgs)
        return self._call_mcp({})
