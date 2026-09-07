# PORTFOLIO.md

## What this project is

An original Vertex AI / Gemini backend — RAG + Agentic AI — built inside
a clone of `GoogleCloudPlatform/generative-ai` to demonstrate production
AI-engineering skills on Google Cloud, distinct from the Azure chatbot,
AWS Bedrock RAG project, and MediQuery in this portfolio. See
`docs/ATTRIBUTION.md` for the explicit line between Google's reference
material and this project's original code, and `docs/FINAL_AUDIT.md` for
what's actually been tested vs. what remains to be run in a real GCP
environment.

## Key technologies actually implemented

- **Google Cloud / Vertex AI**: Gemini generation + structured output,
  Vertex AI embeddings, Vertex AI Vector Search adapter (real code,
  requires a live GCP project to exercise — see `FINAL_AUDIT.md`)
- **Cloud Storage** adapter for document ingestion (`GCSDocumentStore`)
- **Docker** (multi-stage-ready Dockerfile, non-root user, health check)
- **GitHub Actions**: lint, type-check, tests, `pip-audit`, CodeQL,
  Docker build (configured and YAML-validated; not yet run against a
  live GitHub repo — see `FINAL_AUDIT.md`)
- **FastAPI + Pydantic v2** for a fully typed API and internal data model
- **MCP (Model Context Protocol)** — a minimal, real client/server
  implementation (JSON-RPC over stdio), not a mock. See "Key limitation,
  stated plainly" below and `docs/MCP.md` for the exact supported subset.

Not listed here because not implemented: BigQuery, Pub/Sub, Cloud
Monitoring dashboards (design only — see `OBSERVABILITY.md`), IAM
provisioning (design only — see `SECURITY.md`/`DEPLOYMENT.md`). A
reviewer who asks "did you actually set up IAM/BigQuery/Pub-Sub" gets an
honest "no — here's why they weren't justified for this scope, and here's
the design for the piece that is closest to needing it," not a bluff.

## AI engineering

- **RAG**: a full pipeline — validation, multi-format extraction,
  overlap-aware chunking, embeddings, vector retrieval, similarity-
  threshold filtering, near-duplicate removal, grounded generation with
  per-source citations (document, filename, page, chunk ID, similarity
  score). Decision rationale for the retrieval architecture in
  `RAG_DESIGN.md`.
- **Agentic AI**: a real tool-calling loop (not a demo stub) with strict
  Pydantic-validated tool schemas, per-tool authorization, execution
  timeouts, a hard iteration cap, and a full step trace for observability
  — tested against malicious/malformed tool inputs, not just the happy
  path (`tests/integration/test_agent_tools_security.py`).
- **Structured outputs**: model JSON responses are validated (required
  fields, types, enums) before being trusted, never used raw.
- **Hallucination mitigation**: the pipeline explicitly distinguishes
  "grounded" vs. "ungrounded" answers rather than always presenting a
  confident-sounding response, and the evaluation harness scores this
  distinction directly (`groundedness_score` in `evaluation/metrics.py`).
- **Evaluation**: precision@k, recall@k, a keyword-based relevance proxy,
  groundedness accuracy, citation correctness, and agent tool-selection
  accuracy — measured (not invented) against a small reproducible
  dataset; see `AI_EVALUATION.md` for the actual numbers and their
  limitations.
- **MCP-based tool use**: the agent reaches two tools
  (`mcp_text_stats`, `mcp_current_datetime`) through a real MCP server
  subprocess rather than an in-process function — the same `ToolRegistry`
  path, same schema validation, same timeout enforcement as the native
  tools, plus an independent server-side validation/timeout layer since a
  subprocess is a different trust boundary. **Key limitation, stated
  plainly**: this is a minimal subset of MCP — JSON-RPC/stdio, tool
  discovery, and tool invocation only, hand-rolled rather than the
  official `mcp` SDK (which couldn't be installed in the network-
  restricted build sandbox — see `docs/MCP.md`). It is not a claim of
  full protocol coverage, resources/prompts support, or official-SDK
  compatibility.

## Production engineering

- **API design**: FastAPI with typed request/response models, explicit
  exception hierarchy mapped to HTTP status codes, request-ID middleware,
  structured JSON logging.
- **Testing**: 72 pytest tests across unit/integration/e2e layers,
  written against mocked/local backends so the whole system is testable
  without GCP credentials.
- **CI/CD**: a single GitHub Actions workflow covering lint, type-check,
  tests, dependency scanning, CodeQL, and Docker build.
- **Security**: AST-restricted tool execution (no `eval`), upload
  validation (type/size/magic-byte checks), explicit tenant-scoping in
  retrieval, and a security document that states real gaps (no auth
  layer) instead of hiding them.
- **Reliability**: retry-with-backoff on model/embedding calls, explicit
  timeouts everywhere external calls happen, a bounded agent loop that
  cannot infinite-loop.
- **Scalability & cost**: config-driven model/retrieval parameters so
  cost/latency tradeoffs are a deployment decision, not a code change;
  see `DEPLOYMENT.md` and `OBSERVABILITY.md` for what's designed but not
  yet measured at scale.

## What I'd point to first in a portfolio review

1. `app/services/agent/agent.py` + `app/services/agent/tools/` — the
   bounded, sandboxed agent loop and its security tests.
2. `app/services/rag/retrieval.py` + `docs/RAG_DESIGN.md` — the
   retrieval-quality decisions and why they were made.
3. `app/mcp/` + `docs/MCP.md` — the one part of this repo with a
   genuinely re-executed, reproducible verification run (real subprocess,
   real timeout-and-kill, confirmed no orphaned processes), specifically
   because it's stdlib-only and could actually run in the build sandbox.
4. `docs/FINAL_AUDIT.md` — because the honesty about what's verified vs.
   not is itself the engineering signal I want a reviewer to see.
