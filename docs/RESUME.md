# RESUME.md

Every bullet below maps to code or a test in this repo — see
`docs/FINAL_AUDIT.md` for the line between "implemented and traced" and
"deployed/live-benchmarked." Update the bracketed items once you've run
`make test` and a real GCP deployment yourself; don't claim "tested" or
"deployed" until then.

## Short (1–2 lines)

Built a Vertex AI / Gemini RAG and Agentic AI platform on FastAPI —
config-driven model abstraction, grounded retrieval with citations, a
sandboxed tool-calling agent, and a metrics-based evaluation harness.

## Standard (3–4 bullets)

- Designed a modular Vertex AI/Gemini abstraction layer (generation,
  embeddings, structured output, tool calling) decoupled from business
  logic via a protocol-based interface, enabling a swappable live/mock
  backend used across the full test suite.
- Built a production-shaped RAG pipeline (validation → multi-format
  extraction → overlap-aware chunking → embeddings → Vertex AI Vector
  Search → similarity-threshold/dedup filtering → grounded generation
  with per-source citations).
- Implemented a bounded agentic-AI loop with strict Pydantic tool
  schemas, per-tool authorization, execution timeouts, and AST-restricted
  (no `eval`) tool execution — covered by tests targeting malicious and
  malformed tool inputs.
- Built a metrics-based evaluation harness (precision@k, recall@k,
  groundedness, citation correctness, agent tool-selection accuracy)
  against a reproducible dataset, plus CI (lint, type-check, tests,
  dependency scanning, CodeQL, Docker build).

## Senior AI Engineer framing

- **Vertex AI / Gemini**: architected a config-driven `AIService`
  abstraction over Gemini generation, embeddings, structured output, and
  function calling, isolating all model SDK usage behind one interface
  so retries, timeouts, and safety settings are enforced in a single
  place rather than duplicated per call site.
- **RAG**: engineered a full retrieval pipeline on Vertex AI Vector
  Search — chosen over managed RAG Engine/Vertex AI Search after an
  explicit tradeoff analysis (documented) — including similarity-
  threshold filtering, near-duplicate suppression, and full source
  provenance (document, filename, page, chunk, tenant) on every citation.
- **Agentic AI**: built a bounded, sandboxed tool-calling agent (strict
  schema validation, per-tool authorization, execution timeouts, hard
  iteration caps, no arbitrary code execution) with a dedicated test
  suite covering prompt-injection-style and malformed-input attacks
  against the tool layer.
- **AI evaluation & MLOps**: implemented a metrics harness (precision@k,
  recall@k, groundedness, citation correctness, tool-selection accuracy)
  producing real, reproducible numbers against a versioned eval dataset;
  wired evaluation into CI as a pipeline stage alongside lint, type
  checks, dependency scanning (`pip-audit`), CodeQL, and a Docker build.
- **Cloud Run / production engineering**: containerized the service
  (non-root user, health check, `$PORT`-aware entrypoint) with a
  documented least-privilege IAM/Secret Manager deployment design.
- **Security**: no `eval`/`exec` in tool execution (AST-restricted
  calculator), upload validation (type/size/magic-byte checks), explicit
  tenant-scoped retrieval, and a security doc that states real gaps
  (no auth layer yet) rather than glossing over them.
- **Observability**: structured JSON logging with request-correlation
  IDs across the API layer, designed for extension into Cloud
  Logging/Monitoring in a live deployment.

## Do not claim (yet)

- "Deployed to production" / "serving live traffic" — not deployed from
  this build; see `FINAL_AUDIT.md` §3.
- Any specific latency, cost, or accuracy number without the word
  "against a mock backend / small dataset" attached, unless you've
  personally re-run `make evaluate` with `GCP_USE_LIVE_VERTEX_AI=true`
  and recorded new numbers.
- "100% test coverage" or "all tests passing" until you've run
  `make test` yourself outside this sandbox (see `FINAL_AUDIT.md` §2).
- Any compliance certification (SOC 2, ISO 27001, HIPAA) — none claimed
  or pursued.
