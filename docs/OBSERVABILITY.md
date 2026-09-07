# OBSERVABILITY.md

## What's implemented

**Structured JSON logging with request correlation** (`app/core/logging.py`):
every log line includes `timestamp`, `level`, `logger`, `message`, and
`request_id` (propagated via a `contextvars.ContextVar`, set by
`request_context_middleware` in `app/main.py` from the incoming
`X-Request-ID` header, or generated if absent, and echoed back in the
response header). This is the format Cloud Logging expects for structured
log ingestion — no extra parsing step needed once deployed.

**Per-stage timing and counts**, emitted via `log_event()` at each pipeline
stage:

| Event | Where | Fields |
|---|---|---|
| `request_completed` | `app/main.py` middleware | method, path, status_code, duration_ms |
| `document_ingested` | `IngestionPipeline.ingest` | document_id, chunk_count, duration_ms |
| `ingestion_failed` | `IngestionPipeline.ingest` | document_id, error |
| `upload_rejected` | `IngestionPipeline.ingest` | filename, reason |
| `rag_answer_generated` | `RagPipeline.answer` | retrieved_chunks, duration_ms |
| `rag_no_grounded_context` | `RagPipeline.answer` | query_len |
| `generation_succeeded` / `generation_failed` | `DefaultAIService` | model, duration_ms, output_tokens / error |
| `embedding_failed` | `DefaultAIService` | error, text_count |
| `agent_completed` / `agent_max_iterations` | `Agent.run` | iterations, stopped_reason, duration_ms |

**What is never logged, by discipline (see `SECURITY.md`):** raw document
text, full prompts, full model responses, credentials, tokens, or full
conversation content — only counts, IDs, durations, and error messages.

**Token usage** is captured on every `GenerationResult`/`EmbeddingResult`
(`input_tokens`, `output_tokens`) but not yet aggregated into a
cost dashboard — see Limitations.

## What this maps to in Cloud Logging / Cloud Monitoring

Not yet wired up in a live project (no GCP access here), but the design:

- JSON logs shipped to stdout are automatically picked up by Cloud Run's
  Cloud Logging integration with no extra agent — the structured fields
  above become queryable log-based fields.
- **Log-based metrics** to create in Cloud Monitoring once deployed:
  `request_completed.duration_ms` (API latency), `generation_succeeded
  .duration_ms`/`output_tokens` (Gemini latency and cost proxy),
  `rag_answer_generated.retrieved_chunks` (retrieval health),
  `agent_max_iterations` count (agent loop health — a rising rate signals
  either a config problem or the model's tool-selection getting worse).
- **Alerting policies** worth setting once real traffic exists: error rate
  on `generation_failed`/`ingestion_failed`, p95 `request_completed
  .duration_ms`, and a nonzero rate of `agent_max_iterations`.

## Health/readiness

`/healthz` (liveness) and `/readyz` (readiness) are separate endpoints
(`app/api/routes/health.py`) — liveness never depends on external services
staying up (a slow Vertex AI shouldn't get the container killed), while a
real deployment's readiness check would additionally verify connectivity
to the vector index endpoint and documents bucket before Cloud Run routes
traffic to a new instance. Currently identical in the local/mock
configuration since there's nothing external to check.

## Limitations

- **No distributed tracing** (e.g. OpenTelemetry spans across the
  ingestion/retrieval/generation stages) — the per-stage duration_ms
  fields give coarse timing, but a single trace ID linking one request's
  spans across embedding, vector query, and generation is not implemented.
- **No cost dashboard.** Token counts are captured per call but not summed
  into a running cost estimate — see `docs/ARCHITECTURE.md` "Cost
  considerations" for the current (complete) state of cost-related work;
  a running `estimated_cost_usd` field (multiplying token counts by
  published per-model pricing) is a concrete next step, not yet built.
- **No log-based metrics or alerting policies have actually been created**
  in a real Cloud Monitoring workspace — this document describes the
  intended mapping, not a verified live dashboard. Mark as
  `UNVERIFIED — REQUIRES LOCAL/GCP ENVIRONMENT`.
