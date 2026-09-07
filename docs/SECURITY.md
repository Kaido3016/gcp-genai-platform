# SECURITY.md

**No compliance certification is claimed** — not SOC 2, not ISO 27001, not
HIPAA. This document describes engineering controls implemented in this
codebase, and gaps that remain, honestly.

## IAM & service accounts

Not yet provisioned in a real GCP project from this environment (no
network access here — see `AUDIT.md` §4). The design (implemented in
`docs/DEPLOYMENT.md`'s setup steps) is:

- A dedicated service account for the Cloud Run service, scoped to exactly
  three roles: `roles/storage.objectAdmin` on the documents bucket only
  (not project-wide), `roles/aiplatform.user` for Vertex AI/Vector Search
  calls, and `roles/secretmanager.secretAccessor` for the specific secrets
  it needs — never `roles/owner` or `roles/editor`.
- No service account key files. Cloud Run injects credentials via the
  attached service account's identity (Application Default Credentials);
  `VertexGenerativeClient`/`VertexEmbeddingClient`/`GCSDocumentStore`/
  `VertexVectorSearchStore` all rely on ADC rather than accepting or
  parsing a key anywhere in this codebase.

## Secret Manager

No secrets are hardcoded or committed. `.env.example` documents every
configurable value and contains no real credentials — `GCP_PROJECT_ID`
etc. are placeholders. In a real deployment, anything genuinely sensitive
(there currently isn't much beyond the GCP project config, since auth to
Vertex AI/GCS uses ADC, not API keys) would be injected via Cloud Run's
Secret Manager integration, not baked into the container image or
environment file.

## Authentication / authorization

**Known gap, stated plainly:** this codebase does not implement end-user
authentication (no login, no JWT/OIDC verification on the FastAPI routes).
`tenant_id` is accepted as a plain request field, which is sufficient to
demonstrate multi-tenant *data scoping* in retrieval (see `Chunk.tenant_id`
filtering in `app/services/storage/vector_store.py`) but is **not** a
security boundary — a caller can claim any `tenant_id`. A real deployment
must put this behind Identity-Aware Proxy or verify a signed token and
derive `tenant_id` server-side from its claims, never trust a client-supplied
value for it. This is called out here rather than glossed over.

Tool authorization (`Tool.allowed_for_all`, see `AGENTS.md`) is
implemented and tested, but currently has nothing privileged to gate since
there's no auth layer feeding `context["is_privileged"]` yet — it's
scaffolding for when one exists, not a claim that privileged tools are
protected today.

## Prompt injection defense

- **Grounded prompts explicitly instruct the model** to answer only from
  provided sources and to say so if the sources don't contain the answer
  (`app/services/rag/retrieval.py::build_grounded_prompt`) — this reduces
  but does not eliminate the risk of a malicious document instructing the
  model to ignore its instructions.
- **Tool arguments are never executed as code** regardless of what a
  prompt-injected document might ask the model to do — the calculator's
  AST allowlist and every tool's strict argument schema apply
  unconditionally (see `AGENTS.md`).
- **Not implemented:** input/output classifiers specifically for
  injection attempts, and instruction-hierarchy tagging of retrieved
  content vs. the system prompt. Flagged as the next control to add before
  ingesting untrusted third-party documents at scale.

## RAG poisoning defense

- **Upload validation** (`app/services/rag/validation.py`) rejects
  disallowed file types, oversized files, empty files, and files whose
  magic bytes don't match their claimed extension (defense against
  extension spoofing) before any content reaches the model.
- **Provenance on every chunk** (`document_id`, `filename`, `source`,
  `tenant_id`) means a poisoned document's influence is always traceable
  back to exactly which upload produced it — supports takedown/audit, not
  prevention.
- **Not implemented:** content-based scanning of uploaded documents for
  known prompt-injection patterns, or a moderation pass before indexing.
  Realistic for a corpus of untrusted third-party uploads; not yet built.

## Tool security

Covered in depth in `AGENTS.md`: strict schema validation, execution
timeouts, no arbitrary code execution, per-tool authorization. Tested
directly against injection attempts in
`tests/integration/test_agent_tools_security.py`.

**MCP tools specifically** (`docs/MCP.md`) get an extra layer because a
subprocess is a different trust domain than an in-process function call:
schema validation happens on both the client (Pydantic) and server
(independent hand-written check) sides; the client kills the subprocess
on timeout or on `close()` rather than ever leaving one running; and
every exception from a tool handler is converted to a structured
JSON-RPC error inside the server, so a crashing tool cannot crash the
server process or leak a raw traceback across the process boundary. This
was genuinely verified via subprocess round trips, including a real
timeout-and-kill — see `docs/MCP.md` "Verification status" for exactly
what was and wasn't run.

## Input validation

- **Uploads:** type allowlist, size cap (`UPLOAD_MAX_FILE_SIZE_MB`,
  default 20MB), non-empty check, magic-byte sanity check.
- **API request bodies:** every request is a Pydantic model with explicit
  field constraints (`min_length`/`max_length` on queries, range limits on
  `top_k`, etc.) — FastAPI rejects malformed bodies with 422 before a
  route handler ever runs.
- **Tool arguments:** see `AGENTS.md`.

## Output validation

`DefaultAIService.generate_structured()` never trusts a model's JSON output
as valid application data — it parses, then checks required fields, types,
and enum membership against the declared schema, raising
`StructuredOutputValidationError` on any mismatch
(`app/services/ai/service.py::_validate_json_against_schema`, tested in
`tests/unit/test_structured_output.py`).

## Secure logging

`app/core/logging.py` emits structured JSON with a request-correlation ID
on every log line. Call sites are responsible for only logging short,
non-sensitive fields (e.g. `document_id`, `chunk_count`, `duration_ms`) —
**no call site in this codebase logs raw document content, full prompts,
full model responses, credentials, or tokens.** This is enforced by
code-review discipline (every `log_event` call was written to pass field
names/counts, not payloads), not by an automated redaction filter — a
real production deployment should add one as defense in depth.

## CORS

`app/main.py` configures an explicit origin allowlist
(`localhost:3000`, `localhost:8501` for local frontend dev) rather than
`allow_origins=["*"]` with credentials — a common CORS misconfiguration
that would allow any site to make authenticated requests. Production
origins must be added explicitly per environment, never wildcarded.

## Dependency security

`pyproject.toml`/`requirements*.txt` pin version ranges rather than
floating `latest`. Actual vulnerability scanning
(`pip-audit`/Dependabot/CodeQL) is configured in CI (see
`.github/workflows/ci.yaml` and `.github/dependabot.yaml`) but **has not
been run against this dependency set in this
environment** (no network access here to install `pip-audit` or resolve
dependencies at all) — this is marked `UNVERIFIED — REQUIRES LOCAL/GCP
ENVIRONMENT` and must be run in CI/locally before trusting these pins.

## Encryption

Cloud Storage and Vertex AI Vector Search encrypt data at rest by default
under Google-managed keys; nothing in this codebase disables that. CMEK
(customer-managed encryption keys) is not configured — reasonable default
for a portfolio project, called out here as the next step for a real
regulated-data deployment.

## Audit logging

Not separately implemented beyond the structured request logs described
above. A real deployment should enable Cloud Audit Logs for IAM/Storage/
Vertex AI admin actions (data-access logs are off by default and cost
extra — a deliberate choice to enable only for the resources that actually
need it, e.g. the documents bucket).
