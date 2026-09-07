"""Pytest tests for app/mcp/protocol.py.

Note on verification status: `app/mcp/protocol.py` itself is stdlib-only
and was directly exercised in the build sandbox — see
`evaluation/_mcp_sandbox_verification.py` for the actual executed
verification (that script avoids importing pytest, which is also
unavailable in this sandbox, so it re-implements these same checks with
plain `assert` statements). *This* file requires pytest and has not been
run here; run it for real via `make test`. See docs/MCP.md and
FINAL_AUDIT.md for the exact distinction."""

import json

import pytest

from app.mcp.protocol import (
    JsonRpcError,
    JsonRpcRequest,
    JsonRpcResponse,
    ProtocolParseError,
    parse_line,
)


def test_request_round_trips_through_json():
    req = JsonRpcRequest(method="tools/call", id=1, params={"name": "calculator"})
    parsed_back = JsonRpcRequest.from_dict(json.loads(req.to_json()))
    assert parsed_back.method == "tools/call"
    assert parsed_back.id == 1
    assert parsed_back.params == {"name": "calculator"}


def test_request_from_dict_rejects_wrong_jsonrpc_version():
    with pytest.raises(ProtocolParseError):
        JsonRpcRequest.from_dict({"jsonrpc": "1.0", "method": "tools/list", "id": 1})


def test_request_from_dict_rejects_missing_method():
    with pytest.raises(ProtocolParseError):
        JsonRpcRequest.from_dict({"jsonrpc": "2.0", "id": 1})


def test_request_defaults_params_to_empty_dict():
    parsed = JsonRpcRequest.from_dict({"jsonrpc": "2.0", "method": "tools/list", "id": 1})
    assert parsed.params == {}


def test_response_success_serializes_without_error_key_populated():
    resp = JsonRpcResponse(id=1, result={"ok": True})
    data = json.loads(resp.to_json())
    assert data["result"] == {"ok": True}
    assert "error" not in data


def test_response_error_round_trips():
    resp = JsonRpcResponse(id=2, error=JsonRpcError(code=-32001, message="Tool not found"))
    data = json.loads(resp.to_json())
    assert data["error"]["code"] == -32001

    parsed_back = JsonRpcResponse.from_dict(data)
    assert parsed_back.error is not None
    assert parsed_back.error.code == -32001
    assert parsed_back.error.message == "Tool not found"


def test_parse_line_valid_json():
    assert parse_line('{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}') == {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
    }


def test_parse_line_rejects_malformed_json():
    with pytest.raises(ProtocolParseError):
        parse_line("{not valid json at all")


def test_parse_line_rejects_empty_string():
    with pytest.raises(ProtocolParseError):
        parse_line("")
