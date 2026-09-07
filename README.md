# GCP GenAI Platform

A Vertex AI / Gemini RAG + Agentic AI backend, built as an original
engineering project layered on top of (not copied from)
`GoogleCloudPlatform/generative-ai`. See `docs/ATTRIBUTION.md` for exactly
what's Google's and what's original, and `docs/FINAL_AUDIT.md` for an
honest status report — what's implemented, what's tested, and what's
still unverified.

## Overview

Upload documents → they're validated, chunked, embedded, and indexed →
ask questions and get answers grounded in your documents with citations →
or use the agentic endpoint, which can reason about when to search your
documents vs. do arithmetic vs. answer directly, with bounded iterations
and sandboxed tool execution.

## Why GCP / Vertex AI

Vertex AI is the only major cloud AI platform that gives you the managed
model (Gemini), the managed embedding model, and the managed vector
index (Vector Search) under one IAM/networking/billing boundary — so the
retrieval and generation legs of a RAG system can share the same service
account, VPC-SC perimeter, and audit log, instead of stitching together a
model API, a separate vector DB vendor, and a separate cloud for compute.
See `docs/RAG_DESIGN.md` for the specific decision to use Vector Search
over the higher-level RAG Engine or Vertex AI Search products.

## Architecture

```
User → FastAPI → Application AI Service → Vertex AI Adapter → Gemini
                        │
                        ├── RAG pipeline → Vector Search → grounded answer + citations
                        └── Agent loop → tool registry (RAG search, calculator, MCP tools) → validated answer
```

Full diagrams and component responsibilities: `docs/ARCHITECTURE.md`.

## Running it locally (no GCP account needed)

```bash
cd gcp-genai-platform
cp .env.example .env          # defaults to the local mock AI backend
make install
make dev                       # http://localhost:8080/docs for interactive API docs

# in another terminal
cd frontend && python3 -m http.server 3000   # http://localhost:3000
```

Everything works end to end against a deterministic local mock AI
backend and in-memory vector store — no GCP project, credentials, or
network access required for local development or the test suite.

## Running against real Vertex AI

1. Follow `docs/DEPLOYMENT.md` to create a GCP project, enable APIs,
   create a service account, a Cloud Storage bucket, and a Vector Search
   index + endpoint.
2. Set `GCP_USE_LIVE_VERTEX_AI=true` plus the `GCP_*` variables in `.env`.
3. `pip install -r requirements-gcp.txt`.

## AI capabilities

- **Gemini** generation and structured (JSON schema) output, behind a
  single `AIService` abstraction (`app/services/ai/`) — no direct SDK
  calls scattered through business logic.
- **RAG**: validation → extraction (PDF/DOCX/TXT) → chunking with overlap
  → embeddings → Vector Search → similarity-threshold + dedup filtering →
  grounded generation with citations (`docs/RAG_DESIGN.md`).
- **Agentic AI**: a bounded tool-calling loop with strict schemas,
  timeouts, and authorization checks (`docs/AGENTS.md`).
- **MCP (Model Context Protocol)**: a minimal, real implementation — one
  local MCP server (two tools: `text_stats`, `current_datetime`) reached
  by the agent through a genuine JSON-RPC-over-stdio client/subprocess
  boundary, not a mock. This is a **subset** of MCP (see `docs/MCP.md`
  for exactly what's supported and what isn't) — not a claim of full
  protocol or official-SDK compatibility.
- **Structured output validation**: every JSON response from the model is
  checked against required fields, types, and enums before being trusted
  as application data.

## Evaluation, security, observability, deployment

- `docs/AI_EVALUATION.md` — metrics, dataset, and real (not fabricated)
  numbers measured against the local mock backend; live-Gemini numbers
  require running `make evaluate` with GCP credentials.
- `docs/SECURITY.md` — IAM design, Secret Manager, input/output
  validation, prompt-injection and RAG-poisoning considerations, and
  explicitly stated gaps (no auth layer yet).
- `docs/OBSERVABILITY.md` — structured logging, correlation IDs, and the
  Cloud Monitoring/Logging integration plan.
- `docs/DEPLOYMENT.md` — exact `gcloud`/Terraform-shaped steps for Cloud
  Run, none of which have been executed from this build environment (see
  `docs/FINAL_AUDIT.md`).
- `docs/MCP.md` — MCP architecture, exactly what subset of the protocol
  is supported, and the genuine (re-executed, reproducible) sandbox
  verification of the client/server transport layer.

## Testing

72 application pytest tests plus 36 MCP-related tests (5 pytest files
covering protocol/server/client/adapter/agent-integration, plus 1
stdlib-only verification script) — 108 total. See `docs/FINAL_AUDIT.md`
§2 for exactly what's covered and, importantly, what has and hasn't
actually been executed given this build's sandboxed, network-less
environment. The MCP transport layer is the one part of this repo that
*was* genuinely executed here (15/15 checks, twice) — everything
requiring pydantic/FastAPI/pytest was traced by hand instead. Run the
rest yourself: `make install && make test`.

## Engineering decisions worth asking about in an interview

See `docs/RAG_DESIGN.md`, `docs/AGENTS.md`, and `INTERVIEW_GUIDE.md` for
the reasoning behind: Vector Search over RAG Engine/Vertex AI Search, the
chunking/overlap strategy, the similarity-threshold recalibration
(`FINAL_AUDIT.md` §5), why the calculator tool uses AST-restricted
evaluation instead of `eval`, and why there's no auth layer yet.
