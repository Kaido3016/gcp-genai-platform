# FINAL_AUDIT.md

Honest status report as of the end of this build. Nothing here is
aspirational — every claim below is either backed by a file in this repo
or explicitly marked unverified.

## 1. What was implemented

**Backend (`app/`, 3,371 lines of Python across ~40 files, including `app/mcp/`):**
- FastAPI app (`app/main.py`) with request-ID middleware, structured JSON
  logging, CORS, and a typed exception handler.
- Config layer (`app/core/config.py`): every model/retrieval/agent/safety
  parameter is env-driven, nothing hardcoded.
- Explicit exception hierarchy (`app/core/exceptions.py`) — no bare
  `except Exception` anywhere in business logic.
- Vertex AI abstraction (`app/services/ai/`): a protocol-based interface,
  a real (lazy-imported) Vertex/Gemini backend, and a local mock backend.
  The mock backend is what every test and the sandbox evaluation run
  actually exercised — the live backend is real code, never executed here.
- RAG pipeline (`app/services/rag/`): upload validation (type/size/magic
  bytes), PDF/DOCX/TXT extraction, paragraph-aware overlapping chunking,
  an ingestion pipeline, and a retrieval layer with similarity
  thresholding, near-duplicate filtering, and context capping.
- Vector store abstraction (`app/services/storage/vector_store.py`): an
  in-memory implementation (used everywhere in this build) and a Vertex AI
  Vector Search implementation (real code, not exercised — needs a
  deployed index).
- Agentic layer (`app/services/agent/`): a tool registry with Pydantic
  argument validation, per-tool authorization flags, thread-based
  execution timeouts, a RAG-search tool, and an AST-restricted calculator
  tool (no `eval`/`exec`), all wired into a bounded agent loop
  (`max_iterations`, `max_tool_calls_per_turn`).
- Structured-output validation (`DefaultAIService._validate_json_against_schema`)
  — required fields, types, and enum values are checked before any model
  JSON output is trusted as application data.
- Document/chat/agent/health API routes.
- **MCP (Model Context Protocol) — added after initial project completion,
  in response to a dedicated verification/implementation pass** (see §8
  below for the full accounting): `app/mcp/protocol.py` (JSON-RPC framing),
  `app/mcp/server.py` (a real stdio MCP server, two tools), `app/mcp/client.py`
  (a real subprocess-based MCP client), and `app/services/agent/tools/mcp_tool.py`
  (the adapter registering MCP tools into the same `ToolRegistry` the
  native tools use). Full architecture and scope in `docs/MCP.md`.

**Frontend (`frontend/index.html`):** a single dependency-free HTML/JS
page — upload, document status list, RAG chat with grounded/ungrounded
indicator and citation chips, an agent mode showing the tool-call trace,
and loading/error states. No framework, no build step, by design.

**Evaluation (`evaluation/`):** a metrics module (precision@k, recall@k,
keyword-based relevance proxy, groundedness, citation correctness), a
JSON eval dataset (`evaluation/datasets/rag_eval_set.json`, 5 RAG cases +
agent tool-selection cases), a real harness (`run_evaluation.py`) wired to
the actual `RagPipeline`/`Agent` classes, a standalone stdlib-only
verification script for RAG (`_sandbox_verification_run.py`) used to get
real numbers in this network-less sandbox — see §4 — and a second,
separate standalone verification script for MCP
(`_mcp_sandbox_verification.py`) — see §8.

**CI/CD (`.github/workflows/ci.yaml`, `.github/dependabot.yaml`):** lint
(ruff), type-check (mypy), unit+integration+e2e tests with coverage,
the evaluation harness, `pip-audit` dependency scanning, CodeQL, and a
Docker build — all as jobs in one workflow. Dependabot covers pip, Docker,
and Actions.

**Docs (`docs/`):** `RAG_DESIGN.md`, `AGENTS.md`, `AI_EVALUATION.md`,
`SECURITY.md`, `ARCHITECTURE.md`, `OBSERVABILITY.md`, `DEPLOYMENT.md` —
all written to describe what's actually implemented plus explicitly
labeled gaps, not an idealized target state.

## 2. Tests written vs. tests actually executed

108 test functions across `tests/unit/`, `tests/integration/`, and
`tests/e2e/`, covering: chunking (including overlap correctness),
upload validation (extension/size/magic-byte checks, path traversal),
the safe calculator (rejects code-injection attempts, malformed syntax),
retry/backoff behavior, the in-memory vector store (ranking, top-k,
tenant isolation, deletion), retrieval filtering (threshold, dedup,
context cap), structured-output validation, the full ingestion pipeline
(success, validation failures, extraction failures, tenant isolation),
the RAG pipeline (grounded vs. ungrounded answers, citation provenance,
latency), agent tool safety (injection attempts, invalid schemas,
oversized input, unknown tools, execution timeout, authorization), the
bounded agent loop (tool selection, max-iterations enforcement, full step
trace), FastAPI end-to-end flows (upload → status → chat → agent,
including error responses), and MCP (protocol framing, server request
handling and malicious inputs, client/subprocess round trips, the
agent-facing MCP tool adapter, and the agent loop actually selecting an
MCP tool).

**Of these, the MCP transport-layer subset was actually verified — see
§8 for the full accounting.** For the remaining ~93 tests (everything
requiring pydantic/FastAPI/pytest):

**`UNVERIFIED — REQUIRES LOCAL/GCP ENVIRONMENT`:** not executed in this
sandbox. `pip install fastapi pydantic ...` was
attempted twice and failed — the sandbox's egress proxy returns
`x-deny-reason: host_not_allowed` for `pypi.org`, confirmed with a direct
`curl` check (network egress is allowed to some hosts but explicitly not
to package indexes). What I could and did verify here without those
dependencies:
- `python3 -m py_compile` against every file in `app/`, `tests/`, and
  `evaluation/` — all pass (no syntax errors), re-confirmed after the MCP
  additions.
- Manual trace-through of test logic against the actual implementation
  during writing (this caught and fixed one real bug — see §5).
- `evaluation/metrics.py` (deliberately stdlib-only, no app imports) —
  independently re-executed in this session with hand-written assertions;

  all passed.
- `evaluation/_sandbox_verification_run.py` — independently re-executed
  in this session; produced byte-identical summary statistics to the
  committed `evaluation/results/sandbox_verification_run.json` (modulo
  measured latency, which varies run to run as expected).
- CI YAML (`ci.yaml`, `dependabot.yaml`) — parsed successfully with
  Python's `yaml.safe_load`.

**Action required from you:** run `make install && make test` (and
`make lint`, `make typecheck`) in an environment with real network access
to get the actual pass/fail results for the 72 pytest tests, the FastAPI
e2e suite, ruff, and mypy. I have not seen these run and am not claiming
they pass — only that they compile and that I traced their logic
carefully against the implementation.

## 3. GCP-dependent verification status

**Not done, and not claimed:** no live Vertex AI/Gemini call, no
deployed Vector Search index, no Cloud Run deployment, no real GCP IAM
setup. This sandbox has neither network access nor GCP credentials (see
`AUDIT.md` §4). `docs/DEPLOYMENT.md` gives the exact commands to do all of
this against a real project; none of them have been run by me.

## 4. Evaluation status

Real, reproducible numbers exist — but only for the **local mock AI
backend against a 5-case dataset**, not for live Gemini quality:

| Metric | Value | Source |
|---|---|---|
| Mean precision@k | 0.60 | `evaluation/results/sandbox_verification_run.json` |
| Mean recall@k | 0.80 | same |
| Mean keyword-relevance proxy | 0.90 | same |
| Groundedness decision accuracy | 0.80 | same |
| Mean citation correctness | 0.60 | same |
| Mean retrieval latency | ~0.3–0.7 ms (in-process, no network) | same, re-measured twice in this session |
| Agent tool-selection accuracy | 1.00 (5/5 cases) | same |

These numbers say the retrieval/grounding/citation *logic* behaves
correctly against a tiny, hand-built dataset with a hash-based mock
embedding model — they say nothing about real Gemini answer quality,
real `text-embedding-005` retrieval quality, or performance at any
meaningful scale or dataset size. `docs/AI_EVALUATION.md` states this
limitation explicitly. Re-running `make evaluate` with
`GCP_USE_LIVE_VERTEX_AI=true` and a larger, real dataset is required
before citing evaluation numbers anywhere claiming real model quality.

## 5. Bugs found and fixed during this build

- An early version of `app/services/agent/agent.py` called `.value` on a
  plain Python string (`call.name`, from `ToolInvocationRequest.name: str`)
  instead of a `ToolName` enum member — would have raised `AttributeError`
  at runtime. Fixed by explicitly parsing `call.name` into a `ToolName`
  via `ToolName(call.name)` with a `try/except ValueError` for unknown
  tool names, which also hardens the agent against a model hallucinating
  a tool name that doesn't exist (now produces a `TOOL_RESULT` step
  saying so instead of crashing).
- The initial cosine-similarity rescaling `(cos + 1) / 2` in
  `InMemoryVectorStore` didn't match the similarity-threshold semantics
  documented in `RAG_DESIGN.md` once tested against the hash-based mock
  embeddings (whose typical cosine similarities cluster much lower than
  real embedding models' do) — changed to `max(cos, 0.0)` and recalibrated
  `RETRIEVAL_SIMILARITY_THRESHOLD` from an initial guess of 0.55 down to
  0.15, with the reasoning documented in `RAG_DESIGN.md`. This threshold
  is specifically calibrated for the mock backend and **will need
  re-tuning against real `text-embedding-005` output**, which has a
  different similarity distribution — flagged in `RAG_DESIGN.md` and
  `AI_EVALUATION.md` rather than left as a silent trap.

## 6. Known limitations (stated plainly, not buried)

- No end-user authentication/authorization layer (`docs/SECURITY.md`
  §Authentication) — `tenant_id` is client-supplied, not a security
  boundary.
- Document/session state is in-process (`IngestionPipeline._registry`,
  `InMemoryVectorStore`) — not persisted, not multi-instance safe. A real
  deployment needs a real database and either Vector Search or a
  persistent index, as documented in `DEPLOYMENT.md`.
- No reranking or query rewriting (deliberately scoped out — see
  `RAG_DESIGN.md` Limitations).
- No streaming responses in the API or frontend yet (Gemini/FastAPI both
  support it; not implemented in this pass to keep scope controlled per
  your Step 8 instruction not to over-invest in frontend polish).
- Evaluation dataset is intentionally small (5 RAG cases) for fast
  iteration — not a claim of statistically meaningful coverage.
- CI workflow is authored and YAML-validated but has never actually run
  on GitHub Actions from this session (no repo push has happened).

## 7. What would need to happen before any of this goes on a resume as "deployed" or "benchmarked"

1. Push to a real GitHub repo, let CI actually run, fix whatever it finds.
2. `make install && make test` locally — confirm the full test suite actually
   pass outside this sandbox.
3. Provision a real GCP project per `DEPLOYMENT.md`, set
   `GCP_USE_LIVE_VERTEX_AI=true`, re-run `make evaluate` against live
   Gemini + Vector Search, and re-tune `RETRIEVAL_SIMILARITY_THRESHOLD`
   for the real embedding model's score distribution.
4. Deploy to Cloud Run, hit `/healthz` from the outside, confirm it's
   actually reachable before calling anything "deployed."

None of steps 1–4 have happened yet. `RESUME.md` and `PORTFOLIO.md` are
written to only claim what's true as of right now — implemented and
locally-traced, not deployed or live-benchmarked — and are worded to be
updated once you complete the steps above.

## 8. MCP verification (dedicated pass, added after initial completion)

A separate verification pass specifically checked MCP (Model Context
Protocol), since a stray, non-functional fragment (`app/mcp/protocol.py`
with no server, client, tests, or docs — referencing files that didn't
exist) was found sitting in the repo. Full write-up: `docs/MCP.md`. This
section is the audit-trail summary.

**Before this pass:** MCP was not implemented. No client, no server, no
agent integration, no tests, zero documentation mentions. (Note for the
record: MCP was also not part of the original 25-phase brief that started
this project — its addition was a separate, later request.)

**After this pass — implemented:**
- `app/mcp/protocol.py`, `app/mcp/server.py`, `app/mcp/client.py` — a
  real JSON-RPC-over-stdio MCP server (two tools: `text_stats`,
  `current_datetime`) and a real subprocess-based client. Stdlib-only by
  design.
- `app/services/agent/tools/mcp_tool.py` — adapter registering both MCP
  tools into the same `ToolRegistry` the native `calculator`/`rag_search`
  tools use, so the agent loop calls them identically.
- Full chain confirmed present in the code: **Agent → ToolRegistry → MCP
  adapter (`mcp_tool.py`) → MCP client → MCP server subprocess → tool
  handler → result → back through the same chain → Agent.**
- Security: schema validation on both client (Pydantic) and server
  (independent hand-written check) sides; independent timeouts on both
  sides; subprocess terminated on timeout/close in every case (verified,
  not just claimed — see below); every tool-handler exception converted
  to a structured JSON-RPC error, never a raw crash; no `eval`/`exec`/
  shell/filesystem/network access in any tool handler.
- Tests: 3 pytest files (`test_mcp_protocol.py`, `test_mcp_server.py`,
  `test_mcp_client_server.py`) plus 2 more covering the agent-facing
  adapter (`test_mcp_tool_adapter.py`, `test_agent_mcp_integration.py`),
  plus one standalone verification script (next paragraph).

**Genuinely executed in this sandbox — not traced, actually run, twice:**
`evaluation/_mcp_sandbox_verification.py`, a stdlib-only script (no
pytest/pydantic needed, unlike the rest of this repo's tests). It calls
`MCPServer.handle_request()` directly for 8 checks and spawns a **real
subprocess** (`python -m app.mcp.server`) talking over actual stdio pipes
via `MCPClient` for 7 more, including a genuine timeout that kills a
genuinely hung subprocess, plus a check that zero orphaned MCP server
processes remain afterward (`ps aux` grep, asserted empty). **Result:
15/15 checks passed, on two separate runs, with the summary JSON
committed at `evaluation/results/mcp_sandbox_verification.json`.** This
is the single most rigorously verified piece of this entire project,
specifically because it's the one part with no third-party dependency
blocking execution here.

**Still `UNVERIFIED — REQUIRES LOCAL/GCP ENVIRONMENT`, same as the rest
of the repo's pydantic-dependent code:**
- `app/services/agent/tools/mcp_tool.py` itself (imports `pydantic` via
  the shared `Tool` base class) — not executed here, traced by hand.
- `tests/unit/test_mcp_tool_adapter.py` and
  `tests/integration/test_agent_mcp_integration.py` — written, traced,
  not run. Run via `make test`.
- The 3 pytest-form MCP test files mirror the manual script's checks for
  CI purposes but were not run *by pytest* here (pytest unavailable) —
  the manual script is the actual evidence; the pytest files are
  traced-equivalent, pending a real `make test` run.

**Explicitly NOT implemented / NOT claimed** (see `docs/MCP.md` for the
full breakdown): the official `mcp` Python SDK (this is a hand-rolled
JSON-RPC subset, not tested against or compatible-by-construction with
the official SDK — no such claim is made anywhere); MCP resources or
prompts (only tool discovery/invocation); a persistent server process
(each call spawns a fresh subprocess — a stated tradeoff, not a hidden
limitation); any GCP integration for MCP (it's a local subprocess
capability, unrelated to Vertex AI); any authorization model beyond the
existing `allowed_for_all=True` default (neither MCP tool needs
privilege gating, so none was built); load/performance testing of the
subprocess-per-call design.

**MCP status, one line:** minimal, real, agent-integrated, and the
transport layer is the most concretely verified code in this repository
— but it's a deliberate subset of the protocol, not full MCP coverage,
and the pydantic-dependent half of the integration is traced, not run.

## 9. Final consolidated status table

Four categories only, as defined for this audit:
**IMPLEMENTED** (code exists, not run here) ·
**LOCALLY VERIFIED** (actually executed in this sandbox, with evidence) ·
**UNVERIFIED — REQUIRES DEPENDENCIES** (blocked by missing pip packages,
not by GCP) · **UNVERIFIED — REQUIRES GCP** (needs real credentials/
infrastructure) · **NOT IMPLEMENTED**. A row can combine IMPLEMENTED with
a GCP/dependency caveat in the Limitation column — that's not a fifth
category, just a note on an IMPLEMENTED row.

| Area | Status | Evidence | Limitation |
|---|---|---|---|
| RAG pipeline | IMPLEMENTED | `app/services/rag/` — validation, extraction, chunking, retrieval, filtering all present | Logic traced by hand against local mock backend; pytest suite (`tests/unit/`, `tests/integration/`) not executed (§2) |
| RAG evaluation | LOCALLY VERIFIED | `evaluation/_sandbox_verification_run.py` re-run twice in this session, byte-identical to committed `evaluation/results/sandbox_verification_run.json` (precision@k 0.6, recall@k 0.8, groundedness 0.8, citation correctness 0.6) | Numbers are against the local mock backend + 5-case dataset only — not a live-Gemini or at-scale result |
| Agentic AI (native tools) | IMPLEMENTED | `app/services/agent/agent.py`, `tools/calculator_tool.py`, `tools/rag_tool.py`; bounded loop, schema validation | pytest suite (`test_agent_loop.py`, `test_agent_tools_security.py`) traced, not executed — requires pydantic |
| MCP | LOCALLY VERIFIED (transport layer only) | `evaluation/_mcp_sandbox_verification.py` — 15/15 checks, real subprocess, real timeout-and-kill, zero orphaned processes, run twice, reproducible | Minimal subset only (JSON-RPC/stdio, tool discovery/invocation) — not full MCP spec, not the official SDK, no resources/prompts/streaming/OAuth. Agent-facing adapter (`mcp_tool.py`) requires pydantic — traced, not executed |
| Prompt injection defense | IMPLEMENTED (partial) | Grounded prompt instructs the model to answer only from provided sources (`build_grounded_prompt`) | No input-side injection detector; `PromptInjectionSuspectedError` exists as scaffolding only, not wired to a detector (`SECURITY.md`) |
| RAG poisoning defense | IMPLEMENTED (partial) | Upload validation (type/size/magic bytes), tenant-scoped retrieval | No content-level scanning of ingested documents for adversarial instructions; not implemented, stated in `SECURITY.md` |
| Security (general) | IMPLEMENTED (partial) | AST-restricted calculator (no `eval`), upload validation, structured exceptions, CORS allowlist, no secrets in source | No authentication/authorization layer — `tenant_id` is client-supplied, explicitly **not** a security boundary (`SECURITY.md`); no compliance certification claimed or pursued (SOC 2 / ISO 27001 / HIPAA) |
| Structured outputs | IMPLEMENTED | `DefaultAIService._validate_json_against_schema` — required fields/types/enums checked before trusting model JSON | Validation logic traced, not pytest-executed |
| Multimodal | NOT IMPLEMENTED | — | Out of scope for this build; base repo's multimodal notebooks were reviewed in `AUDIT.md` but nothing was built here |
| Observability | IMPLEMENTED | Structured JSON logs + request-correlation IDs (`app/core/logging.py`, `app/main.py` middleware) — real code, runs whenever the app runs | No live Cloud Logging/Monitoring wiring (`UNVERIFIED — REQUIRES GCP`); no distributed tracing; no cost dashboard (`OBSERVABILITY.md`) |
| Frontend | IMPLEMENTED | `frontend/index.html` — upload, status, chat with citations, agent tool-trace view, loading/error states | Not executed against a live backend in this session (would require the FastAPI server running, which itself needs pydantic/FastAPI installed); no streaming UI |
| CI/CD | IMPLEMENTED | `.github/workflows/ci.yaml` (lint, type-check, tests, evaluation, `pip-audit`, CodeQL, Docker build), `.github/dependabot.yaml` — both YAML-validated in this session | UNVERIFIED — REQUIRES DEPENDENCIES / GitHub: never run on actual GitHub Actions (no repo push has happened) |
| Docker | IMPLEMENTED | `Dockerfile` — non-root user, health check, `$PORT`-aware entrypoint | UNVERIFIED — REQUIRES DEPENDENCIES: `docker build` not run (no container runtime / network access to pull the base image in this sandbox); syntax-reviewed only |
| Vertex AI / Gemini | IMPLEMENTED | `app/services/ai/vertex_backend.py` — real `google-genai` SDK calls, lazy-imported | UNVERIFIED — REQUIRES GCP: never executed against a live project; all tests/evaluation ran against the local mock backend instead |
| Cloud Run | IMPLEMENTED (config only) | `docs/DEPLOYMENT.md` gives exact `gcloud run deploy` commands; `Dockerfile` is Cloud-Run-shaped | UNVERIFIED — REQUIRES GCP: never deployed, never reached from outside this sandbox |
| Cloud Storage | IMPLEMENTED | `app/services/storage/document_store.py` — `GCSDocumentStore`, real `google-cloud-storage` calls | UNVERIFIED — REQUIRES GCP: no bucket created, never executed |
| Vector Search | IMPLEMENTED | `app/services/storage/vector_store.py` — `VertexVectorSearchStore`, real `google-cloud-aiplatform` calls | UNVERIFIED — REQUIRES GCP: no index/endpoint deployed; all retrieval tests used `InMemoryVectorStore` instead |
| Secret Manager / IAM | NOT IMPLEMENTED (design only) | `docs/SECURITY.md` and `docs/DEPLOYMENT.md` describe the intended least-privilege service account and Secret Manager usage | No service account created, no IAM bindings applied, no secrets stored anywhere — this is a design document, not a deployed control |
| Pub/Sub | NOT IMPLEMENTED | — | Deliberately excluded — `docs/ARCHITECTURE.md` states no async fan-out need at this scale; not a gap, a scoping decision |
| Documentation | LOCALLY VERIFIED (for internal consistency) | Cross-checked in this session: 2 pre-existing broken references fixed (`COST_OPTIMIZATION.md`, `CICD.md`), zero remaining broken doc links found by manual scan, overclaiming scan across all 15 docs found no uncorrected instances (§10) | "Locally verified" here means checked for consistency/accuracy by re-reading, not that every technical claim inside every doc has independently been re-derived beyond what's stated in this table |

## 10. Overclaiming audit (this pass)

A targeted scan for "production," "deployed," "fully verified/compliant,"
"enterprise-ready," "SLA," "99.9%," "HIPAA/SOC 2/ISO/GDPR," "benchmark,"
"real users/real-world," and MCP-specific overclaims ("full MCP,"
"official SDK compatible," "OAuth," "streaming," "resources/prompts")
was run across all 16 docs in this repo (`README.md`, `PORTFOLIO.md`,
`FINAL_AUDIT.md`, `../AUDIT.md`, `ARCHITECTURE.md`, `SECURITY.md`,
`OBSERVABILITY.md`, `DEPLOYMENT.md`, `AI_EVALUATION.md`, `AGENTS.md`,
`MCP.md`, `RAG_DESIGN.md`, `INTERVIEW_GUIDE.md`, `RESUME.md`,
`ATTRIBUTION.md`, `frontend/README.md`).

**Result: no uncorrected overclaiming found.** Every hit on every
searched term was already correctly negated/hedged from earlier passes
in this build (e.g. "no compliance certification is claimed," "not a
production-ready value," "not full MCP coverage," "not deployed from
this build"). The two genuinely broken doc references found and fixed in
this pass (§ above) were missing-file citations, not overclaiming — they
pointed to a `COST_OPTIMIZATION.md`/`CICD.md` that never existed, not to
an inflated claim. No wording changes were needed beyond those two fixes.

## 11. What remains genuinely unverified — the honest gap list

- The ~93 pydantic/FastAPI-dependent tests (of 108 total) have never been
  run by pytest, anywhere, by anyone, in this build. `make test` has
  never executed.
- Ruff and mypy have never run against this codebase.
- `docker build` has never run — the Dockerfile has been read, not built.
- No GCP project, service account, bucket, Vector Search index, or Cloud
  Run service has ever been created for this project.
- No live Gemini/embedding call has ever been made.
- No GitHub Actions run has ever happened (no repo push).
- No real user, no real traffic, no real cost, no real latency-at-scale
  number exists anywhere in this project.

## 12. Next actions required before calling any part of this "deployed" or "production-ready"

1. `make install && make test` in a real environment with network access
   — get actual pass/fail for the 108 tests, ruff, and mypy.
2. `make build` (or `docker build .`) — confirm the image actually
   builds.
3. Push to a real GitHub repo and let `.github/workflows/ci.yaml` run for
   real; fix whatever it finds.
4. Provision a real GCP project per `DEPLOYMENT.md` (service account,
   bucket, Vector Search index/endpoint), set
   `GCP_USE_LIVE_VERTEX_AI=true`, and re-run `make evaluate` to get real
   Gemini/embedding-backed numbers — expect `RETRIEVAL_SIMILARITY_THRESHOLD`
   to need re-tuning for the real embedding model's score distribution.
5. Deploy to Cloud Run, confirm `/healthz` is reachable from the outside,
   and only then update `RESUME.md`/`PORTFOLIO.md` to say "deployed."
