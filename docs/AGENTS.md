# AGENTS.md

## Architecture

```
User query
  -> Agent.run() [app/services/agent/agent.py]
       loop (max AGENT_MAX_ITERATIONS iterations, default 6):
         -> AIService.generate_with_tools(query, tools, history)
         -> if no tool_calls returned: final answer, stop
         -> else, for each requested tool call (capped at
            AGENT_MAX_TOOL_CALLS_PER_TURN per turn, default 8):
              -> ToolRegistry.execute(tool, args, timeout, context)
                   1. look up tool -> ToolNotFoundError if unknown
                   2. authorization check -> ToolAuthorizationError if denied
                   3. validate args against strict Pydantic schema
                      -> ToolInputValidationError if invalid
                   4. run in a worker thread with a timeout
                      -> ToolTimeoutError if it doesn't finish in time
                      -> ToolExecutionError if it raises
              -> result appended to conversation history, loop continues
  -> iteration budget exhausted without a final answer
       -> return best-effort fallback answer built from successful tool
          outputs so far, stopped_reason="max_iterations"
```

Every step (thought/tool_call/tool_result/final_answer) is recorded in
`AgentResponse.steps` for observability and for the evaluation harness to
score tool-selection accuracy — nothing about the agent's reasoning is
hidden from the API response.

## Tools

| Tool | Purpose | Authorization |
|---|---|---|
| `rag_search` | Query the ingested document corpus (same retrieval + threshold/dedup logic as `/chat`) | Open to all callers |
| `calculator` | Evaluate a restricted arithmetic expression | Open to all callers |
| `mcp_text_stats` | Word/character/sentence counts + reading time, via an external MCP server subprocess | Open to all callers |
| `mcp_current_datetime` | Current UTC date/time, via the same MCP server | Open to all callers |

The last two are not native Python functions — they're backed by a real
MCP (Model Context Protocol) server running as a separate subprocess,
speaking JSON-RPC over stdio. The agent loop calls them identically to
the native tools (same `ToolRegistry`, same schema validation, same
timeout enforcement); the only difference is what happens inside
`Tool.run()`. Full architecture, security controls, and — importantly —
exactly what has and hasn't been verified: `docs/MCP.md`.

Adding a privileged tool (e.g. a write-capable BigQuery query, or an
external API with side effects) means setting `allowed_for_all = False` on
that `Tool` subclass and having the caller's `context["is_privileged"]`
reflect a real authorization decision made upstream (e.g. from an auth
token's claims) — not implemented here since there's no auth layer yet to
back it (see `SECURITY.md` "Known gaps").

## Tool schemas (Phase 7/8 — strict validation)

Every tool's arguments are a Pydantic model in `app/schemas/agent.py`
(`RagSearchArgs`, `CalculatorArgs`), registered in `TOOL_ARG_SCHEMAS` and
exposed to the model as a JSON schema via `Tool.json_schema()`. Arguments
are validated with `model_validate()` **before** the tool ever runs — a
malformed or out-of-range argument (e.g. `top_k=999` when the schema caps
it at 20, or a missing required field) produces a `ToolInputValidationError`
result, never a crash or a silent pass-through to the tool body.

## Safety controls

- **No arbitrary code execution, ever.** The calculator tool does not use
  `eval`/`exec`. Expressions are parsed with `ast.parse` and walked against
  an explicit allowlist of node types (`Constant`, `BinOp`, `UnaryOp`) and
  operators (`+ - * / % **`) in `app/services/agent/tools/calculator_tool.py`.
  Anything else — function calls, attribute access, name lookups, imports —
  is rejected with `ToolExecutionError` before it can execute.
  Tested in `tests/unit/test_calculator_tool.py` and
  `tests/integration/test_agent_tools_security.py` against actual injection
  attempts (`__import__('os').system(...)`, `open(...).read()`, etc.).
- **Bounded iterations.** `AGENT_MAX_ITERATIONS` (default 6) hard-stops the
  loop; tested in `tests/integration/test_agent_loop.py` with a
  `max_iterations=1` config to confirm the loop terminates deterministically
  rather than looping.
- **Tool timeouts.** Each tool runs in a `ThreadPoolExecutor` worker with
  `AGENT_TOOL_TIMEOUT_SECONDS` (default 10); a tool that hangs is killed at
  the result-collection boundary and reported as `ToolTimeoutError`, not
  allowed to block the agent loop indefinitely. Tested with a
  deliberately-slow test tool.
- **Tool authorization.** `Tool.allowed_for_all` plus a `context` dict
  passed through the whole call chain — tested with a synthetic privileged
  tool in both the allowed and denied cases.
- **Explicit exception hierarchy**, not bare `except Exception` — every
  failure mode above has its own type in `app/core/exceptions.py`, so
  callers (and logs) can distinguish "the model asked for a bad argument"
  from "the tool itself broke" from "the tool took too long."

## Failure handling

If the agent hits its iteration cap without a final answer, it does not
error out — it returns the best-effort synthesis of whatever tool outputs
succeeded so far, with `stopped_reason="max_iterations"`, so the caller
always gets a usable (if incomplete) response rather than a 5xx.

## Limitations

- **No cross-tool state beyond conversation history.** Tools don't share a
  scratchpad or working memory beyond what's serialized into `history`.
- **The mock backend's tool-routing is a simple heuristic** (regex for
  "looks like arithmetic," otherwise default to `rag_search` if not
  already tried) — it is not a stand-in for real Gemini function-calling
  quality, only for exercising the agent *loop mechanics* offline. See
  `AI_EVALUATION.md` for the measured tool-selection accuracy on the tiny
  eval set (2 cases — not a claim of general accuracy).
- **No real authorization backend.** `context["is_privileged"]` is always
  `False` today because there's no authentication layer populating it —
  see `SECURITY.md`.
- **`ThreadPoolExecutor`-based timeouts don't forcibly kill a hung native
  call** — a genuinely stuck thread (e.g. blocked on a network call inside
  a future tool) will keep running in the background after the timeout is
  reported to the caller; this is a known Python limitation (no true thread
  cancellation), not something this implementation works around. Real
  external-API tools should implement their own request-level timeouts as
  defense in depth rather than relying solely on this outer timeout.
