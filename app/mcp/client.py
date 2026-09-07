"""A real MCP client using a subprocess + stdio transport.

Deliberately stdlib-only (subprocess, json, threading) so the actual
transport can be exercised without the application dependency stack.
"""

from __future__ import annotations

import json
import subprocess
import threading
from typing import Any

from app.core.exceptions import ToolExecutionError, ToolNotFoundError, ToolTimeoutError
from app.mcp.protocol import (
    METHOD_INITIALIZE,
    METHOD_TOOLS_CALL,
    METHOD_TOOLS_LIST,
    TOOL_NOT_FOUND,
    TOOL_TIMEOUT,
    ProtocolParseError,
    parse_line,
)


class MCPProtocolError(Exception):
    """Raised on malformed/unexpected JSON-RPC traffic from the server."""


class MCPClient:
    """One client instance = one server subprocess."""

    def __init__(self, command: list[str], *, call_timeout_seconds: float = 5.0):
        self._command = command
        self._call_timeout_seconds = call_timeout_seconds
        self._process: subprocess.Popen | None = None
        self._next_id = 1
        self._lock = threading.Lock()

    def __enter__(self) -> MCPClient:
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def start(self) -> None:
        self._process = subprocess.Popen(
            self._command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._call("__initialize__", METHOD_INITIALIZE, {})

    def close(self) -> None:
        if self._process is None:
            return
        try:
            if self._process.stdin:
                self._process.stdin.close()
            self._process.terminate()
            self._process.wait(timeout=2)
        except Exception:
            self._process.kill()
        finally:
            self._process = None

    def list_tools(self) -> list[dict[str, Any]]:
        result = self._call("__list__", METHOD_TOOLS_LIST, {})
        return result.get("tools", [])

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        result = self._call(
            f"call-{name}",
            METHOD_TOOLS_CALL,
            {"name": name, "arguments": arguments},
        )
        return result.get("content")

    def _call(self, label: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if self._process is None or self._process.stdin is None or self._process.stdout is None:
            raise ToolExecutionError(
                "MCP client is not started (call start() or use as a context manager)."
            )

        with self._lock:
            request_id = self._next_id
            self._next_id += 1
            request_line = json.dumps(
                {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
            )

            try:
                self._process.stdin.write(request_line + "\n")
                self._process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                raise ToolExecutionError(
                    f"MCP server process is not accepting input: {exc}"
                ) from exc

            response_line = self._read_response_with_timeout()

        try:
            response = parse_line(response_line)
        except ProtocolParseError as exc:
            raise MCPProtocolError(
                f"Malformed JSON-RPC from MCP server for '{label}': {exc}"
            ) from exc

        if response.get("id") != request_id:
            raise MCPProtocolError(
                f"MCP response id mismatch for '{label}': expected {request_id}, "
                f"got {response.get('id')!r}"
            )

        if "error" in response and response["error"] is not None:
            error = response["error"]
            code = error.get("code")
            message = error.get("message", "unknown MCP error")
            if code == TOOL_NOT_FOUND:
                raise ToolNotFoundError(message)
            if code == TOOL_TIMEOUT:
                raise ToolTimeoutError(message)
            raise ToolExecutionError(f"MCP error {code}: {message}")

        return response.get("result", {})

    def _read_response_with_timeout(self) -> str:
        """Read one line from subprocess stdout with a hard timeout."""
        read_line: str | None = None
        read_error: Exception | None = None
        done = threading.Event()

        def _reader() -> None:
            nonlocal read_line, read_error
            try:
                read_line = self._process.stdout.readline()  # type: ignore[union-attr]
            except Exception as exc:  # noqa: BLE001
                read_error = exc
            finally:
                done.set()

        thread = threading.Thread(target=_reader, daemon=True)
        thread.start()
        finished = done.wait(timeout=self._call_timeout_seconds)

        if not finished:
            self.close()
            raise ToolTimeoutError(
                f"MCP call exceeded client-side timeout of {self._call_timeout_seconds}s"
            )

        if read_error is not None:
            raise ToolExecutionError(f"Error reading from MCP server: {read_error}")

        if not read_line:
            raise ToolExecutionError(
                "MCP server closed its output stream unexpectedly (empty read)."
            )
        return read_line
