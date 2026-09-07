"""Pytest integration tests: real MCPClient <-> subprocess MCPServer round
trips. This exact flow (initialize, tools/list, tools/call, error cases,
timeout) was manually executed and verified in the build sandbox using a
plain-Python script since pytest is unavailable there — see
`evaluation/_mcp_sandbox_verification.py` and `docs/MCP.md` "Verification
status" for the actual command output. *This* pytest file itself was not
run in that sandbox; run via `make test`."""

import sys

import pytest

from app.core.exceptions import ToolExecutionError, ToolNotFoundError, ToolTimeoutError
from app.mcp.client import MCPClient

SERVER_COMMAND = [sys.executable, "-m", "app.mcp.server"]


def test_list_tools_returns_expected_tools():
    with MCPClient(SERVER_COMMAND, call_timeout_seconds=3.0) as client:
        names = {t["name"] for t in client.list_tools()}
    assert "text_stats" in names
    assert "current_datetime" in names
    assert "_slow_test_tool" not in names  # not test_mode, so not exposed


def test_call_text_stats_over_subprocess():
    with MCPClient(SERVER_COMMAND, call_timeout_seconds=3.0) as client:
        result = client.call_tool("text_stats", {"text": "hello there friend"})
    assert result["word_count"] == 3


def test_call_current_datetime_over_subprocess():
    with MCPClient(SERVER_COMMAND, call_timeout_seconds=3.0) as client:
        result = client.call_tool("current_datetime", {})
    assert "iso8601_utc" in result


def test_unknown_tool_raises_tool_not_found():
    with MCPClient(SERVER_COMMAND, call_timeout_seconds=3.0) as client:
        with pytest.raises(ToolNotFoundError):
            client.call_tool("does_not_exist", {})


def test_invalid_arguments_raise_tool_execution_error():
    with MCPClient(SERVER_COMMAND, call_timeout_seconds=3.0) as client:
        with pytest.raises(ToolExecutionError):
            client.call_tool("text_stats", {})  # missing required 'text'


def test_client_side_timeout_kills_subprocess(monkeypatch):
    monkeypatch.setenv("MCP_TEST_MODE", "true")
    with MCPClient(SERVER_COMMAND, call_timeout_seconds=0.5) as client:
        with pytest.raises(ToolTimeoutError):
            client.call_tool("_slow_test_tool", {"seconds": 5})
        # process should have been terminated by the timeout handler
        assert client._process is None


def test_client_reusable_for_multiple_sequential_calls():
    with MCPClient(SERVER_COMMAND, call_timeout_seconds=3.0) as client:
        r1 = client.call_tool("text_stats", {"text": "a b"})
        r2 = client.call_tool("text_stats", {"text": "a b c d"})
    assert r1["word_count"] == 2
    assert r2["word_count"] == 4
