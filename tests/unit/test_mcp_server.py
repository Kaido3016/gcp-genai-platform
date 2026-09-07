"""Pytest tests for app/mcp/server.py's MCPServer.handle_request.

Note on verification status: `app/mcp/server.py` is itself stdlib-only
and was directly exercised in the build sandbox (see
`evaluation/_mcp_sandbox_verification.py`), but *this file* imports
pytest, which is unavailable in this sandbox — not run here. Run via
`make test`. See docs/MCP.md / FINAL_AUDIT.md."""

import pytest

from app.mcp.server import MCPServer


@pytest.fixture
def server() -> MCPServer:
    return MCPServer(tool_timeout_seconds=1.0, test_mode=True)


def test_initialize(server):
    resp = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert resp["result"]["serverInfo"]["name"] == "gcp-genai-platform-mcp-server"


def test_tools_list_exposes_expected_tools(server):
    resp = server.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    names = {t["name"] for t in resp["result"]["tools"]}
    assert "text_stats" in names
    assert "current_datetime" in names


def test_text_stats_success(server):
    resp = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "text_stats", "arguments": {"text": "one two three"}},
        }
    )
    assert resp["result"]["content"]["word_count"] == 3


def test_current_datetime_success(server):
    resp = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "current_datetime", "arguments": {}},
        }
    )
    assert "iso8601_utc" in resp["result"]["content"]


def test_unknown_tool_returns_structured_error_not_exception(server):
    resp = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "delete_everything", "arguments": {}},
        }
    )
    assert resp["error"]["code"] == -32001


def test_unknown_method_returns_structured_error(server):
    resp = server.handle_request(
        {"jsonrpc": "2.0", "id": 6, "method": "shutdown_server", "params": {}}
    )
    assert resp["error"]["code"] == -32601


def test_missing_required_field_rejected(server):
    resp = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "text_stats", "arguments": {}},
        }
    )
    assert resp["error"]["code"] == -32602


def test_wrong_type_rejected(server):
    resp = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "tools/call",
            "params": {"name": "text_stats", "arguments": {"text": 42}},
        }
    )
    assert resp["error"]["code"] == -32602


def test_oversized_text_rejected(server):
    huge_text = "x" * 30_000  # exceeds MAX_TEXT_LENGTH's maxLength schema entry
    resp = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {"name": "text_stats", "arguments": {"text": huge_text}},
        }
    )
    assert resp["error"]["code"] == -32602


def test_tool_timeout_enforced(server):
    resp = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"name": "_slow_test_tool", "arguments": {"seconds": 5}},
        }
    )
    assert resp["error"]["code"] == -32003


def test_slow_test_tool_not_exposed_outside_test_mode():
    prod_server = MCPServer(tool_timeout_seconds=1.0, test_mode=False)
    resp = prod_server.handle_request(
        {"jsonrpc": "2.0", "id": 11, "method": "tools/list", "params": {}}
    )
    names = {t["name"] for t in resp["result"]["tools"]}
    assert "_slow_test_tool" not in names


def test_handler_exception_becomes_structured_error_not_crash(server):
    def boom(params):
        raise RuntimeError("simulated handler crash")

    server._tools["text_stats"].handler = boom
    resp = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 12,
            "method": "tools/call",
            "params": {"name": "text_stats", "arguments": {"text": "hi"}},
        }
    )
    assert resp["error"]["code"] == -32004
    assert "simulated handler crash" in resp["error"]["message"]
