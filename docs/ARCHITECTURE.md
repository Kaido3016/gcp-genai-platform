# ARCHITECTURE.md

## Component overview

```
                         ┌─────────────────────┐
                         │   Frontend (SPA)     │
                         │  upload/chat/agent    │
                         └──────────┬───────────┘
                                    │ HTTPS
                         ┌──────────▼───────────┐
                         │   Cloud Run service    │
                         │   (FastAPI, this repo) │
                         └──────────┬───────────┘
              ┌─────────────────────┼─────────────────────┐
              │                     │                       │
   ┌──────────▼─────────┐ ┌────────▼────────┐   ┌──────────▼─────────┐
   │  Cloud Storage       │ │ Vertex AI /      │   │ Vertex AI           │
   │  (document uploads)  │ │ Gemini           │   │ Vector Search        │
   └───────────────────────┘ │ (generation +    │   │ (retrieval index)    │
                              │  embeddings)      │   └───────────────────┘
                              └──────────────────┘
   Cross-cutting:  Secret Manager (config secrets) · IAM (least-privilege
   service account) · Cloud Logging (structured JSON logs) · Cloud
   Monitoring (custom metrics) · Artifact Registry (container images) ·
   Cloud Build / GitHub Actions (CI/CD)
```

Only services with a concrete justification are included. Explicitly
**not** used: Pub/Sub (no async fan-out need at this scale — ingestion is
synchronous request/response, which is fine for the document sizes this
demo targets; a real high-volume ingestion pipeline would add it, and
that's called out below as a scaling note, not silently pretended-in), and
BigQuery (no analytical/tabular workload here — the calculator tool is a
placeholder for where a real BigQuery tool would live if the flagship use
case needed structured-data queries).

## Request flow (chat)

```
Client -> POST /chat {query, tenant_id}
  -> FastAPI route (app/api/routes/chat.py)
  -> RagPipeline.answer() (app/services/rag/pipeline.py)
       -> AIService.embed_texts(query)      [Vertex AI embeddings, or local mock]
       -> VectorStore.query(embedding)      [Vertex AI Vector Search, or in-memory]
       -> filter_and_rank()                 [similarity threshold, dedup, cap]
       -> build_grounded_prompt()
       -> AIService.generate_text(prompt)   [Gemini, or local mock]
  <- ChatResponse {answer, citations, grounded, latency_ms}
```

## RAG ingestion flow

```
Client -> POST /documents/upload (multipart file)
  -> validate_upload()             [type/size/magic-byte checks]
  -> DocumentStore.save()          [Cloud Storage, or local filesystem]
  -> extract_text()                [pypdf / python-docx / plain text]
  -> build_chunks()                [paragraph-aware windows + overlap]
  -> AIService.embed_texts()       [batched]
  -> VectorStore.upsert()
  <- DocumentUploadResponse {document_id, status, chunk_count}
```

Every failure mode above (`DocumentValidationError`,
`DocumentProcessingError`, `EmbeddingError`, `VectorStoreError`) maps to a
distinct exception and updates `DocumentStatus` to `FAILED` with a
recorded `error_message` rather than silently dropping the document — see
`app/services/rag/ingestion.py`.

## Agent flow

See `AGENTS.md` for the full loop diagram and safety controls
(bounded iterations, tool timeouts, strict schemas, no arbitrary code
execution). Two of the agent's tools (`mcp_text_stats`,
`mcp_current_datetime`) are backed by a real local MCP server subprocess
rather than in-process Python — see `docs/MCP.md` for that architecture
and its independently verified transport layer. This is a local-only
capability today (a subprocess on the same machine as the API), not a
GCP service; it sits inside the "Cloud Run service" box in the component
diagram above, not as a separate box of its own.

## Authentication flow

**Not implemented** — see `SECURITY.md` "Known gap." The intended design
for a real deployment: Cloud Run behind Identity-Aware Proxy or a
verified OIDC token, with `tenant_id` derived server-side from the
token's claims rather than accepted as a client-supplied field as it is
today.

## Security boundaries

- Cloud Run service account has access only to its own documents bucket
  and the specific Vertex AI/Vector Search resources it needs (see
  `SECURITY.md`) — not project-wide access.
- The frontend never talks to GCP directly; every call goes through the
  FastAPI service, which is the only component holding GCP credentials.
- CORS is an explicit allowlist, not a wildcard (`app/main.py`).

## Failure handling

Every external dependency call (Gemini generation, embeddings, vector
store, document store) goes through `call_with_retry`
(`app/services/ai/retry.py`) with exponential backoff and a bounded retry
count, and raises a specific typed exception on exhaustion rather than
propagating a raw SDK exception or silently returning empty/default data.
See `app/core/exceptions.py` for the full hierarchy.

## Scalability

- **Stateless Cloud Run service** — horizontal scaling is just more
  container instances; no in-process session state (the current
  in-memory document registry in `IngestionPipeline` is a portfolio-scale
  simplification — see Limitations below).
- **Vertex AI Vector Search** is built for high-QPS ANN retrieval at a
  scale the in-memory linear-scan fallback is not — that's precisely why
  it's the chosen production backend (see `RAG_DESIGN.md`).
- **Batched embedding calls** (`EMBED_BATCH_SIZE`, default 16) reduce
  per-request overhead during ingestion of large documents.

**Known scaling limitation, stated plainly:** `IngestionPipeline._registry`
(document status tracking) is an in-process Python dict. On Cloud Run with
more than one instance, a status check could hit a different instance than
the one that processed the upload, returning a stale/missing result. A
real deployment needs this backed by Firestore or Cloud SQL — noted as a
concrete "if I had another day" item for `INTERVIEW_GUIDE.md`, not silently
left as if it weren't a problem.

## Cost considerations

No separate `COST_OPTIMIZATION.md` exists — this section is the complete
cost writeup, not a pointer to a missing file. Cloud Run scales to zero
when idle, Gemini Flash is the default model specifically for
cost/latency (see `app/core/config.py`'s documented rationale),
embeddings are batched (`EMBED_BATCH_SIZE`), and
`RETRIEVAL_MAX_CONTEXT_CHUNKS` bounds prompt size (and therefore
per-request token cost) regardless of how many chunks pass the
similarity threshold. No caching layer or aggregated cost dashboard is
implemented yet — token counts are captured per call
(`GenerationResult`/`EmbeddingResult`) but not summed into a running
estimate; see `docs/OBSERVABILITY.md` Limitations for the same gap noted
from the metrics side. No real-traffic cost has been measured, since
nothing has been deployed (`docs/FINAL_AUDIT.md` §3).
