"""Standalone MCP verification — NOT part of the pytest suite.

This sandbox has no `pytest` or `pydantic` installed (see FINAL_AUDIT.md
§2 for why). `app/mcp/protocol.py`, `app/mcp/server.py`, and
`app/mcp/client.py` are deliberately stdlib-only, so unlike the rest of
this codebase they *can* actually be imported and run here. This script
exercises the real client -> subprocess -> server round trip (not a
simulation/reimplementation, unlike `_sandbox_verification_run.py` for
RAG) and asserts on the results, writing a report of exactly what passed.

It does NOT exercise `app/services/agent/tools/mcp_tool.py` (the
pydantic-dependent adapter that plugs these tools into the agent's
ToolRegistry) or the agent loop itself — those require pydantic/FastAPI
and were traced by hand instead; see docs/FINAL_AUDIT.md and
tests/unit/test_mcp_tool_adapter.py / tests/integration/test_agent_mcp_integration.py.

Run: python3 -m evaluation._mcp_sandbox_verification
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.exceptions import ToolExecutionError, ToolNotFoundError, ToolTimeoutError  # noqa: E402
from app.mcp.client import MCPClient  # noqa: E402
from app.mcp.server import MCPServer  # noqa: E402

SERVER_COMMAND = [sys.executable, "-m", "app.mcp.server"]

checks: list[dict] = []


def check(name: str, fn) -> None:
    start = time.perf_counter()
    try:
        fn()
        checks.append(
            {
                "name": name,
                "passed": True,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            }
        )
        print(f"PASS  {name}")
    except Exception as exc:  # noqa: BLE001 - this script's whole job is to report failures, not hide them
        checks.append(
            {
                "name": name,
                "passed": False,
                "error": f"{type(exc).__name__}: {exc}",
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            }
        )
        print(f"FAIL  {name}: {type(exc).__name__}: {exc}")


# --- Direct server checks (no subprocess) -----------------------------------


def check_server_initialize():
    server = MCPServer(test_mode=True)
    resp = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert resp["result"]["serverInfo"]["name"] == "gcp-genai-platform-mcp-server"


def check_server_tools_list():
    server = MCPServer(test_mode=False)
    resp = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    names = {t["name"] for t in resp["result"]["tools"]}
    assert names == {"text_stats", "current_datetime"}, names


def check_server_text_stats():
    server = MCPServer(test_mode=False)
    resp = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "text_stats", "arguments": {"text": "a b c"}},
        }
    )
    assert resp["result"]["content"]["word_count"] == 3


def check_server_rejects_unknown_tool():
    server = MCPServer(test_mode=False)
    resp = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "nope", "arguments": {}},
        }
    )
    assert resp["error"]["code"] == -32001


def check_server_rejects_missing_field():
    server = MCPServer(test_mode=False)
    resp = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "text_stats", "arguments": {}},
        }
    )
    assert resp["error"]["code"] == -32602


def check_server_rejects_wrong_type():
    server = MCPServer(test_mode=False)
    resp = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "text_stats", "arguments": {"text": 1}},
        }
    )
    assert resp["error"]["code"] == -32602


def check_server_enforces_timeout():
    server = MCPServer(test_mode=True, tool_timeout_seconds=0.5)
    resp = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "_slow_test_tool", "arguments": {"seconds": 3}},
        }
    )
    assert resp["error"]["code"] == -32003


def check_server_hides_test_tool_in_production_mode():
    server = MCPServer(test_mode=False)
    resp = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    names = {t["name"] for t in resp["result"]["tools"]}
    assert "_slow_test_tool" not in names


# --- Real subprocess round-trip checks --------------------------------------


def check_client_server_list_tools():
    with MCPClient(SERVER_COMMAND, call_timeout_seconds=3.0) as client:
        names = {t["name"] for t in client.list_tools()}
        assert names == {"text_stats", "current_datetime"}, names


def check_client_server_text_stats_call():
    with MCPClient(SERVER_COMMAND, call_timeout_seconds=3.0) as client:
        result = client.call_tool(
            "text_stats", {"text": "Model Context Protocol enables tool use."}
        )
        assert result["word_count"] == 6, result


def check_client_server_current_datetime_call():
    with MCPClient(SERVER_COMMAND, call_timeout_seconds=3.0) as client:
        result = client.call_tool("current_datetime", {})
        assert "iso8601_utc" in result and "unix_timestamp" in result


def check_client_raises_tool_not_found():
    with MCPClient(SERVER_COMMAND, call_timeout_seconds=3.0) as client:
        try:
            client.call_tool("does_not_exist", {})
            raise AssertionError("expected ToolNotFoundError")
        except ToolNotFoundError:
            pass


def check_client_raises_on_invalid_params():
    with MCPClient(SERVER_COMMAND, call_timeout_seconds=3.0) as client:
        try:
            client.call_tool("text_stats", {})
            raise AssertionError("expected ToolExecutionError")
        except ToolExecutionError:
            pass


def check_client_side_timeout_kills_subprocess():
    import os

    os.environ["MCP_TEST_MODE"] = "true"
    client = MCPClient(SERVER_COMMAND, call_timeout_seconds=0.5)
    client.start()
    start = time.perf_counter()
    try:
        client.call_tool("_slow_test_tool", {"seconds": 5})
        raise AssertionError("expected ToolTimeoutError")
    except ToolTimeoutError:
        elapsed = time.perf_counter() - start
        assert elapsed < 2.0, f"timeout took too long to fire: {elapsed}s"
        assert client._process is None, "subprocess was not cleaned up after timeout"
    finally:
        os.environ.pop("MCP_TEST_MODE", None)


def check_no_orphaned_processes_after_run():
    import subprocess as sp

    out = sp.run(["ps", "aux"], capture_output=True, text=True).stdout
    running = [line for line in out.splitlines() if "app.mcp.server" in line and "grep" not in line]
    assert running == [], f"orphaned MCP server processes found: {running}"


def main() -> None:
    check("server: initialize", check_server_initialize)
    check(
        "server: tools/list exposes exactly text_stats + current_datetime", check_server_tools_list
    )
    check("server: text_stats computes correct word count", check_server_text_stats)
    check(
        "server: unknown tool -> structured TOOL_NOT_FOUND error", check_server_rejects_unknown_tool
    )
    check("server: missing required field -> INVALID_PARAMS", check_server_rejects_missing_field)
    check("server: wrong argument type -> INVALID_PARAMS", check_server_rejects_wrong_type)
    check("server: slow handler -> TOOL_TIMEOUT enforced", check_server_enforces_timeout)
    check(
        "server: test-only tool hidden outside test_mode",
        check_server_hides_test_tool_in_production_mode,
    )
    check("client+subprocess: tools/list round trip", check_client_server_list_tools)
    check("client+subprocess: text_stats round trip", check_client_server_text_stats_call)
    check(
        "client+subprocess: current_datetime round trip", check_client_server_current_datetime_call
    )
    check(
        "client+subprocess: unknown tool raises ToolNotFoundError",
        check_client_raises_tool_not_found,
    )
    check(
        "client+subprocess: invalid params raise ToolExecutionError",
        check_client_raises_on_invalid_params,
    )
    check(
        "client: client-side timeout fires and kills subprocess",
        check_client_side_timeout_kills_subprocess,
    )
    check("no orphaned MCP server processes remain", check_no_orphaned_processes_after_run)

    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)
    summary = {"passed": passed, "total": total, "all_passed": passed == total, "checks": checks}

    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)
    (results_dir / "mcp_sandbox_verification.json").write_text(json.dumps(summary, indent=2))

    print(f"\n{passed}/{total} checks passed.")
    if passed != total:
        sys.exit(1)


if __name__ == "__main__":
    main()
