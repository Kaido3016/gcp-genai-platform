# MCP.md

## Status

**Implemented, minimal, and genuinely verified end-to-end in this sandbox
— but only the transport layer, and only against the local mock AI
backend's tool routing.** Not GCP-verified, not load-tested, not deployed.
See "Verification status" below for the exact, non-fabricated details.

## Why this exists

MCP (Model Context Protocol) lets an agent call tools exposed by an
independent server process over a standard JSON-RPC wire protocol,
instead of every tool being a Python function living inside the agent's
own process. This project implements one real MCP server with two tools,
wired into the same agent loop that already runs `CalculatorTool` and
`RagSearchTool`, to demonstrate the pattern without building an
unjustified ecosystem of superficial servers.

## Architecture

```
Agent loop (app/services/agent/agent.py)
   │  selects a tool from ToolRegistry, same as CalculatorTool/RagSearchTool
   ▼
McpTextStatsTool / McpCurrentDatetimeTool  (app/services/agent/tools/mcp_tool.py)
   │  validates args via Pydantic (McpTextStatsArgs / McpCurrentDatetimeArgs)
   │  spawns a fresh MCPClient per call
   ▼
MCPClient (app/mcp/client.py)               ── subprocess boundary ──
   │  JSON-RPC over stdio, client-side timeout, kills the process on timeout
   ▼
MCPServer subprocess (app/mcp/server.py)    entry point: `python -m app.mcp.server`
   │  validates args again (server-side schema check — different trust domain)
   │  runs the handler in a timeout-bounded thread
   ▼
text_stats / current_datetime handlers (plain functions, no filesystem/network/subprocess access)
```

`app/mcp/protocol.py` is the shared JSON-RPC 2.0 message-framing module
both the client and server import.

## Files

| File | Role | Depends on pydantic/FastAPI? |
|---|---|---|
| `app/mcp/protocol.py` | JSON-RPC request/response dataclasses, method/error constants | No — stdlib only |
| `app/mcp/server.py` | The MCP server: tool registry, schema validation, timeout-bounded execution, stdio loop | No — stdlib only |
| `app/mcp/client.py` | The MCP client: subprocess spawn/teardown, JSON-RPC calls, client-side timeout | No — stdlib only |
| `app/services/agent/tools/mcp_tool.py` | Adapter: wraps `MCPClient` calls as `Tool` subclasses for `ToolRegistry` | Yes — imports `app.services.agent.tools.base.Tool` (Pydantic-based) |
| `app/schemas/agent.py` (additions) | `ToolName.MCP_TEXT_STATS` / `MCP_CURRENT_DATETIME`, their Pydantic arg schemas | Yes |
| `app/core/config.py` (addition) | `McpConfig` — enabled flag, server command, client timeout | Yes |
| `app/dependencies.py` (addition) | Registers the two MCP tools into `get_tool_registry()` when `MCP_ENABLED=true` | Yes |

The transport layer (`protocol.py`, `server.py`, `client.py`) is
deliberately stdlib-only, specifically so it could be genuinely executed
and verified in this network-less, dependency-restricted sandbox — see
below.

## Tools exposed

- **`text_stats(text: str)`** → word/character/sentence counts and an
  estimated reading time. Useful for agent queries like "how long is
  this" without re-running retrieval.
- **`current_datetime()`** → the server's current UTC time (ISO 8601 +
  Unix timestamp). A genuinely useful grounding tool — the model has no
  reliable way to know "today's date" on its own.

A third tool, `_slow_test_tool`, exists **only** when the server is
started with `MCPServer(test_mode=True)` (or `MCP_TEST_MODE=true` for the
CLI entry point) — it sleeps on command so timeout enforcement is
directly, deterministically testable. It is never listed by `tools/list`
in normal (non-test) mode — verified by
`check_server_hides_test_tool_in_production_mode` in
`evaluation/_mcp_sandbox_verification.py`.

## Security controls, and where each is enforced

| Control | Enforced where | How |
|---|---|---|
| Strict schemas | Client (Pydantic) **and** server (hand-written JSON-Schema-style check) | `McpTextStatsArgs`/`McpCurrentDatetimeArgs` on the client side; `_validate_params()` in `server.py` on the server side — two independent trust domains, neither trusts the other |
| Authorization | Client, via the existing `ToolRegistry.execute` authorization check | `Tool.allowed_for_all` (currently `True` for both MCP tools — no privileged gating needed yet, same honest caveat as the native tools; see `SECURITY.md`) |
| Validation | Both sides, before any handler runs | Required fields, types, and (for `text`) a max length, checked before the subprocess is even spawned (client) and again before the handler executes (server) |
| Timeouts | Both sides, independently | `MCPClient(call_timeout_seconds=...)` on the client; `MCPServer(tool_timeout_seconds=...)` on the server — either one firing is sufficient to bound a call |
| Bounded execution | Server (worker thread) + client (subprocess kill on timeout) | `concurrent.futures.ThreadPoolExecutor` with `.result(timeout=...)` on the server; `MCPClient.close()` terminates the subprocess on timeout, error, or normal shutdown — no leaked processes (verified, see below) |
| Safe error handling | Server | Every exception from a tool handler is caught and converted to a structured JSON-RPC error (`TOOL_EXECUTION_ERROR`), never a raw traceback over the wire or a crashed process |
| No arbitrary code execution | Both | Tool handlers are a fixed, explicit registry (like `CalculatorTool`'s AST-restricted evaluator) — there is no "run this code" tool, and no `eval`/`exec`/shell access anywhere in the MCP code path |

## Untrusted content handling

`MCPClient.call_tool()` returns whatever JSON-serializable data the
server's handler produced, as plain data — it is never executed,
never used to build a shell command, and never trusted as anything more
than text. It flows into the agent's tool-result history exactly like
`RagSearchTool`'s retrieved chunk text or `CalculatorTool`'s numeric
result: as untrusted content that becomes part of the next prompt, not as
instructions the client acts on. This project's two tools happen to
return small, well-typed dicts (counts, a timestamp) with no attacker-
controlled free text in them, so today there is no injection surface to
speak of from these specific tools — but the handling code makes no
assumption that a future MCP tool's output is safe, which is why it isn't
special-cased or auto-trusted anywhere in `mcp_tool.py`.

## Verification status — read this before citing any MCP claim

**What was genuinely executed in this sandbox** (no pytest, no pydantic
available — see `FINAL_AUDIT.md` §2 for why):
`evaluation/_mcp_sandbox_verification.py` — a stdlib-only script that
directly calls `MCPServer.handle_request()` for 8 checks, and spawns a
**real subprocess** running `python -m app.mcp.server` and talks to it
through `MCPClient` over actual stdio pipes for 7 more checks, including
a genuine timeout that kills a genuinely hung subprocess, and a check
that no orphaned server processes remain afterward. Result: **15/15
passed**, run twice for reproducibility. Raw output saved to
`evaluation/results/mcp_sandbox_verification.json`.

This proves: the JSON-RPC framing, the server's tool dispatch/validation/
timeout logic, and the client's subprocess lifecycle and timeout handling
all genuinely work, over a real (if local, single-machine) process
boundary.

**What this does NOT prove, and is not claimed:**
- The pydantic-dependent adapter (`mcp_tool.py`) and its registration in
  `ToolRegistry`/`Agent` were **not executed** — `pydantic` could not be
  installed here (network blocked, same root cause documented in
  `FINAL_AUDIT.md` §2). `tests/unit/test_mcp_tool_adapter.py` and
  `tests/integration/test_agent_mcp_integration.py` were written and
  traced by hand against the implementation, not run. Run `make test`
  yourself to execute them.
- No GCP integration was exercised — this MCP server is entirely local
  and has nothing to do with Vertex AI directly; it's an independent
  capability reachable from the same agent loop.
- No performance/load testing — the subprocess-per-call design has
  known startup-latency overhead, stated as a tradeoff above, not
  measured under load.
- The full pytest files (`tests/unit/test_mcp_protocol.py`,
  `tests/unit/test_mcp_server.py`,
  `tests/integration/test_mcp_client_server.py`) mirror the checks in
  `_mcp_sandbox_verification.py` in proper pytest form for CI, but
  weren't run by pytest itself here (pytest unavailable) — the manual
  script is what was actually executed; treat the pytest files as
  traced-correct-by-construction, confirmed via the equivalent
  hand-run script's identical logic, until `make test` runs them for
  real.

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `MCP_ENABLED` | `true` | If `false`, no MCP tools are registered with the agent at all |
| `MCP_CALL_TIMEOUT_SECONDS` | `5.0` | Client-side per-call timeout |
| `MCP_TEST_MODE` (server subprocess env, not an app setting) | unset | If `"true"`, the server also exposes `_slow_test_tool` for timeout testing |

## What would change for a "real" MCP deployment

- Use the official `mcp` Python SDK instead of this hand-rolled JSON-RPC
  layer, once it can actually be installed (blocked here only by sandbox
  network restrictions, not a technical obstacle).
- A persistent server process (or a small pool) instead of spawning one
  per call, if latency under real load matters.
- Tools that do more than local computation (e.g., a real external API)
  would need the authorization model extended beyond the current
  `allowed_for_all=True` default — flagged, not implemented, since
  neither current tool needs it.
