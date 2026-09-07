# INTERVIEW_GUIDE.md

Every answer below points at real code or a real, documented decision —
not a generic textbook answer. File references let you re-ground yourself
before a live conversation.

**1. Why Vertex AI?**
One IAM/networking/billing boundary for the model (Gemini), the embedding
model, and the vector index (Vector Search), instead of stitching a model
API, a third-party vector DB, and separate auth together. See `README.md`
"Why GCP."

**2. Why Gemini specifically?**
Native function-calling and JSON-schema structured output on the same API
surface used for generation — both used directly in `app/services/ai/base.py`
(`generate_with_tools`, `generate_structured`). Flash is the default model
(`GenerationConfig.model_name` in `app/core/config.py`) because the
flagship use case is latency/cost-sensitive RAG and tool-reasoning, not
long-form deep reasoning; swapping to a Pro-tier model is a one-line env
change, not a code change.

**3. Why GCP instead of AWS (which I've also built on)?**
Not a "GCP is better" claim — a portfolio-scoping one: the AWS project
already covers Bedrock + RAG, so this project deliberately goes deeper on
the pieces AWS project doesn't emphasize (agentic tool-calling with
safety controls, structured-output validation, an evaluation harness).

**4. How does the RAG pipeline work end to end?**
Upload → `validate_upload` (type/size/magic bytes) → `extract_text`
(PDF/DOCX/TXT) → `build_chunks` (paragraph-aware, overlapping) →
`embed_texts` → `VectorStore.upsert`. Query → embed → `VectorStore.query`
(top-k) → `filter_and_rank` (similarity threshold, dedup, context cap) →
`build_grounded_prompt` → `generate_text` → citations built from the
exact chunks used. Every step is a separate, independently tested module
(`app/services/rag/`).

**5. Why Vertex AI Vector Search over RAG Engine or Vertex AI Search?**
Full reasoning in `docs/RAG_DESIGN.md`: Vector Search is the lowest-level
primitive that still requires (and demonstrates) real retrieval
engineering — index management, similarity thresholds, metadata
filtering — versus delegating that to a managed corpus or a black-box
search product. Tradeoff acknowledged: more operational surface to own.

**6. How do you evaluate RAG quality?**
`evaluation/metrics.py`: precision@k, recall@k, a keyword-based relevance
proxy (explicitly documented as a cheap stand-in for model-based
relevance, not a claim of semantic evaluation), a groundedness score that
specifically penalizes "claims grounded, zero citations," and citation
correctness. Numbers on record (`docs/AI_EVALUATION.md`) were measured
against the local mock backend on a 5-case dataset — I'd be upfront that
this validates the *pipeline logic*, not real Gemini/embedding quality,
until `make evaluate` is re-run with `GCP_USE_LIVE_VERTEX_AI=true`.

**7. How do you reduce hallucinations?**
Three layers: (a) retrieval — similarity threshold drops low-relevance
context rather than always forcing top-k into the prompt
(`filter_and_rank`); (b) prompting — the grounded prompt explicitly
instructs the model to say so if sources don't contain the answer
(`build_grounded_prompt`); (c) the response schema itself carries a
`grounded: bool` so the caller (UI or evaluation) can distinguish a
grounded answer from a fallback one, instead of hiding the distinction.

**8. How does the agent work?**
A bounded loop (`app/services/agent/agent.py`): the model proposes tool
calls, they're validated against strict Pydantic schemas, checked for
authorization, executed with a per-tool timeout in a worker thread, and
results are fed back into history. Stops on either a final answer or
`AgentConfig.max_iterations` — deterministically, never an infinite loop,
tested directly in `test_agent_respects_max_iterations`.

**9. How do you prevent prompt injection?**
Partially addressed, stated honestly: the grounded-answer prompt
instructs the model to answer only from provided sources, which limits
(but doesn't eliminate) injected instructions hiding in retrieved
document text. Not yet implemented: input-side heuristic scanning
(`PromptInjectionSuspectedError` exists in `app/core/exceptions.py` as
scaffolding, not wired to a detector yet). I'd say this plainly rather
than overclaim — see `docs/SECURITY.md` "Prompt injection."

**10. How do you secure tool calling specifically?**
No `eval`/`exec` anywhere — the calculator tool parses expressions with
Python's `ast` module and walks a strict allowlist of node types
(`safe_arithmetic_eval` in `calculator_tool.py`), tested against a direct
`__import__(...)` injection attempt. Every tool's arguments go through a
Pydantic schema before execution; unknown tools and malformed arguments
return a structured error, never crash the agent
(`tests/integration/test_agent_tools_security.py`).

**11. How do you deploy on Cloud Run?**
Documented, not yet executed (`docs/DEPLOYMENT.md` and
`docs/FINAL_AUDIT.md` §3): non-root Docker image, `$PORT`-aware Uvicorn
entrypoint, health check, a dedicated least-privilege service account
(no `roles/owner`), secrets via Secret Manager rather than baked into the
image or env file.

**12. How do you monitor Gemini in production?**
Design in `docs/OBSERVABILITY.md`: structured JSON logs with
request-correlation IDs (implemented and in use today — see
`app/core/logging.py` and the request middleware in `app/main.py`),
extended in production with Cloud Logging/Monitoring for latency, token
usage, and cost per call — not yet wired to real Cloud Monitoring from
this environment.

**13. How do you control costs?**
Config-driven `max_output_tokens`, retrieval `top_k`/`max_context_chunks`
caps, and batch-sized embedding calls (`EmbeddingConfig.batch_size`) —
all tunable without code changes. No caching layer yet; flagged as a
next step in `docs/DEPLOYMENT.md`/cost notes rather than implemented and
overclaimed.

**14. How do you handle model/service failures?**
`call_with_retry` (`app/services/ai/retry.py`) — exponential backoff,
only on explicitly retryable exceptions, never masking a non-retryable
error. Distinct exception types (`ModelTimeoutError`,
`ModelSafetyBlockError`, `VectorStoreError`, etc.) so callers can react
differently instead of one generic failure path.

**15. How would you scale this system?**
Today: in-memory vector store and an in-process document registry — a
deliberate, stated limitation for this build's scope (`FINAL_AUDIT.md`
§6). Scaling path: swap `InMemoryVectorStore` for the already-written
`VertexVectorSearchStore`, back the document registry with Firestore/
Cloud SQL, and let Cloud Run's autoscaling handle request concurrency —
the abstraction boundaries (`VectorStore`, `DocumentStore`, `AIService`)
exist specifically so this swap doesn't touch business logic.

**16. What would you change for real enterprise production?**
Add an actual auth layer (IAP or verified OIDC token → server-derived
`tenant_id`, since today's `tenant_id` is client-supplied and explicitly
called out as not a security boundary in `SECURITY.md`), persistent
storage, real Cloud Monitoring dashboards, a prompt-injection detector,
and a much larger evaluation dataset run against live Gemini before
trusting any number for a go/no-go decision.
