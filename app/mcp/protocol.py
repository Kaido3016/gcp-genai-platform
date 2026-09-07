"""JSON-RPC 2.0 message framing and MCP method/error constants.

Deliberately stdlib-only (dataclasses, json, typing — nothing else) so
this module, and everything built directly on it (`server.py`,
`client.py`), can be imported and executed even in an environment where
pydantic/FastAPI aren't installed. That's not a style preference: it's
what let the transport layer of this MCP implementation actually be run
and verified in the sandbox that built this project — see
evaluation/_mcp_sandbox_verification.py and docs/MCP.md "Verification
status" for exactly what that proves and doesn't prove.

Implements the subset of MCP (Model Context Protocol) needed for tool
discovery and invocation over stdio: `initialize`, `tools/list`,
`tools/call`, plus standard JSON-RPC 2.0 error codes. This is a hand-rolled
implementation of the wire protocol, not the official `mcp` Python SDK
(that package could not be installed in this network-restricted sandbox —
see docs/MCP.md for why, and for the upgrade path to the official SDK).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

JSONRPC_VERSION = "2.0"

METHOD_INITIALIZE = "initialize"
METHOD_TOOLS_LIST = "tools/list"
METHOD_TOOLS_CALL = "tools/call"
SUPPORTED_METHODS = {METHOD_INITIALIZE, METHOD_TOOLS_LIST, METHOD_TOOLS_CALL}

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

TOOL_NOT_FOUND = -32001
TOOL_UNAUTHORIZED = -32002
TOOL_TIMEOUT = -32003
TOOL_EXECUTION_ERROR = -32004


class ProtocolParseError(Exception):
    """Raised when a raw line cannot be parsed as a JSON-RPC message."""


@dataclass
class JsonRpcRequest:
    method: str
    id: int | str | None
    params: dict[str, Any] = field(default_factory=dict)
    jsonrpc: str = JSONRPC_VERSION

    def to_json(self) -> str:
        return json.dumps(
            {"jsonrpc": self.jsonrpc, "id": self.id, "method": self.method, "params": self.params}
        )

    @staticmethod
    def from_dict(data: dict) -> JsonRpcRequest:
        if data.get("jsonrpc") != JSONRPC_VERSION or "method" not in data:
            raise ProtocolParseError(f"Malformed JSON-RPC request: {data!r}")
        return JsonRpcRequest(
            method=data["method"], id=data.get("id"), params=data.get("params", {}) or {}
        )


@dataclass
class JsonRpcError:
    code: int
    message: str
    data: Any = None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            d["data"] = self.data
        return d


@dataclass
class JsonRpcResponse:
    id: int | str | None
    result: Any = None
    error: JsonRpcError | None = None
    jsonrpc: str = JSONRPC_VERSION

    def to_json(self) -> str:
        payload: dict[str, Any] = {"jsonrpc": self.jsonrpc, "id": self.id}
        if self.error is not None:
            payload["error"] = self.error.to_dict()
        else:
            payload["result"] = self.result
        return json.dumps(payload)

    @staticmethod
    def from_dict(data: dict) -> JsonRpcResponse:
        if data.get("jsonrpc") != JSONRPC_VERSION:
            raise ProtocolParseError(f"Malformed JSON-RPC response: {data!r}")
        err = None
        if "error" in data and data["error"] is not None:
            e = data["error"]
            err = JsonRpcError(code=e["code"], message=e["message"], data=e.get("data"))
        return JsonRpcResponse(id=data.get("id"), result=data.get("result"), error=err)


def parse_line(line: str) -> dict:
    """Parse one newline-delimited JSON-RPC message."""
    try:
        return json.loads(line)
    except json.JSONDecodeError as exc:
        raise ProtocolParseError(f"Invalid JSON on the wire: {exc}") from exc
