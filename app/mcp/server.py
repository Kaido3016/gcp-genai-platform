"""A real, minimal MCP server over stdio.

Implements `initialize`, `tools/list`, and `tools/call` per the JSON-RPC
framing in `protocol.py`. Exposes exactly two tools and enforces validation,
structured errors, and bounded execution.
"""

from __future__ import annotations

import concurrent.futures
import re
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.mcp.protocol import (
    INVALID_PARAMS,
    METHOD_INITIALIZE,
    METHOD_NOT_FOUND,
    METHOD_TOOLS_CALL,
    METHOD_TOOLS_LIST,
    TOOL_EXECUTION_ERROR,
    TOOL_NOT_FOUND,
    TOOL_TIMEOUT,
    JsonRpcError,
    ProtocolParseError,
    parse_line,
)

MAX_TEXT_LENGTH = 20_000
DEFAULT_TOOL_TIMEOUT_SECONDS = 5.0
SERVER_NAME = "gcp-genai-platform-mcp-server"
SERVER_VERSION = "0.1.0"


class ToolSpec:
    def __init__(
        self,
        name: str,
        description: str,
        parameters_schema: dict[str, Any],
        handler: Callable[[dict[str, Any]], Any],
    ):
        self.name = name
        self.description = description
        self.parameters_schema = parameters_schema
        self.handler = handler


def _validate_params(schema: dict[str, Any], params: dict[str, Any]) -> str | None:
    """Validate tool arguments with a minimal dependency-free schema."""
    if not isinstance(params, dict):
        return "params must be an object"

    for field_name in schema.get("required", []):
        if field_name not in params:
            return f"missing required field: {field_name}"

    type_map = {"string": str, "integer": int, "number": (int, float), "boolean": bool}
    for field_name, value in params.items():
        prop = schema.get("properties", {}).get(field_name)
        if not prop:
            continue
        expected = type_map.get(prop.get("type", ""))
        if expected and not isinstance(value, expected):
            return (
                f"field '{field_name}' expected type {prop.get('type')}, got {type(value).__name__}"
            )
        max_length = prop.get("maxLength")
        if max_length is not None and isinstance(value, str) and len(value) > max_length:
            return f"field '{field_name}' exceeds max length {max_length}"
    return None


def _text_stats_handler(params: dict[str, Any]) -> dict[str, Any]:
    text = params["text"][:MAX_TEXT_LENGTH]
    words = re.findall(r"\S+", text)
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    word_count = len(words)
    return {
        "character_count": len(text),
        "word_count": word_count,
        "sentence_count": len(sentences),
        "estimated_reading_time_seconds": round((word_count / 200) * 60, 1),
    }


def _current_datetime_handler(params: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(UTC)
    return {"iso8601_utc": now.isoformat(), "unix_timestamp": int(now.timestamp())}


def _slow_test_handler(params: dict[str, Any]) -> dict[str, Any]:
    """Test-only timeout helper."""
    time.sleep(float(params.get("seconds", 2.0)))
    return {"slept": True}


def _build_tool_specs(test_mode: bool) -> dict[str, ToolSpec]:
    specs = {
        "text_stats": ToolSpec(
            name="text_stats",
            description=(
                "Compute word/character/sentence counts and an estimated "
                "reading time for a piece of text."
            ),
            parameters_schema={
                "type": "object",
                "properties": {"text": {"type": "string", "maxLength": MAX_TEXT_LENGTH}},
                "required": ["text"],
            },
            handler=_text_stats_handler,
        ),
        "current_datetime": ToolSpec(
            name="current_datetime",
            description=(
                "Get the current UTC date and time. Use this for any question "
                "involving 'today', 'now', or relative dates."
            ),
            parameters_schema={"type": "object", "properties": {}, "required": []},
            handler=_current_datetime_handler,
        ),
    }
    if test_mode:
        specs["_slow_test_tool"] = ToolSpec(
            name="_slow_test_tool",
            description="Test-only tool that sleeps; not exposed outside test_mode.",
            parameters_schema={
                "type": "object",
                "properties": {"seconds": {"type": "number"}},
                "required": [],
            },
            handler=_slow_test_handler,
        )
    return specs


class MCPServer:
    """Handle JSON-RPC requests and return structured responses."""

    def __init__(
        self,
        *,
        tool_timeout_seconds: float = DEFAULT_TOOL_TIMEOUT_SECONDS,
        test_mode: bool = False,
    ):
        self._tools = _build_tool_specs(test_mode)
        self._tool_timeout_seconds = tool_timeout_seconds
        self._initialized = False

    def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        request_id = request.get("id")
        method = request.get("method")

        if method == METHOD_INITIALIZE:
            self._initialized = True
            return self._ok(
                request_id,
                {
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                    "capabilities": {"tools": {}},
                },
            )

        if method == METHOD_TOOLS_LIST:
            tools = [
                {"name": t.name, "description": t.description, "inputSchema": t.parameters_schema}
                for t in self._tools.values()
            ]
            return self._ok(request_id, {"tools": tools})

        if method == METHOD_TOOLS_CALL:
            return self._handle_tools_call(request_id, request.get("params", {}) or {})

        return self._err(request_id, METHOD_NOT_FOUND, f"Unknown method: {method}")

    def _handle_tools_call(self, request_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        tool_name = params.get("name")
        arguments = params.get("arguments", {}) or {}

        if not isinstance(tool_name, str) or tool_name not in self._tools:
            return self._err(request_id, TOOL_NOT_FOUND, f"Tool not found: {tool_name}")

        spec = self._tools[tool_name]
        validation_error = _validate_params(spec.parameters_schema, arguments)
        if validation_error:
            return self._err(request_id, INVALID_PARAMS, validation_error)

        start = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(spec.handler, arguments)
            try:
                result = future.result(timeout=self._tool_timeout_seconds)
            except concurrent.futures.TimeoutError:
                return self._err(
                    request_id,
                    TOOL_TIMEOUT,
                    f"Tool '{tool_name}' exceeded {self._tool_timeout_seconds}s timeout",
                )
            except Exception as exc:  # noqa: BLE001
                return self._err(
                    request_id,
                    TOOL_EXECUTION_ERROR,
                    f"Tool '{tool_name}' raised: {exc}",
                )

        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        return self._ok(
            request_id,
            {"content": result, "isError": False, "_duration_ms": duration_ms},
        )

    @staticmethod
    def _ok(request_id: Any, result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _err(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": JsonRpcError(code=code, message=message).to_dict(),
        }


def run_stdio_loop(server: MCPServer, *, in_stream=None, out_stream=None) -> None:
    """Run the newline-delimited JSON-RPC stdio transport."""
    in_stream = in_stream or sys.stdin
    out_stream = out_stream or sys.stdout

    for raw_line in in_stream:
        line = raw_line.strip()
        if not line:
            continue
        try:
            request = parse_line(line)
        except ProtocolParseError as exc:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": str(exc)},
            }
            out_stream.write(response_to_json_line(response))
            out_stream.flush()
            continue

        response = server.handle_request(request)
        out_stream.write(response_to_json_line(response))
        out_stream.flush()


def response_to_json_line(response: dict[str, Any]) -> str:
    import json

    return json.dumps(response) + "\n"


if __name__ == "__main__":
    import os

    test_mode = os.environ.get("MCP_TEST_MODE") == "true"
    timeout = float(os.environ.get("MCP_TOOL_TIMEOUT_SECONDS", str(DEFAULT_TOOL_TIMEOUT_SECONDS)))
    run_stdio_loop(MCPServer(tool_timeout_seconds=timeout, test_mode=test_mode))
