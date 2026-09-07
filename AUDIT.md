# AUDIT.md — Repository Audit (Phase 1)

**Source repo:** `GoogleCloudPlatform/generative-ai`
**Scope of this audit:** structural inventory of the full repo, reusability assessment, and gap analysis against the goal of a coherent, production-oriented Vertex AI / Gemini portfolio platform.
**Status:** No code has been modified. This is inspection only.

---

## 1. Repository shape (as-is)

This is **not an application** — it is Google's official cookbook of ~330 standalone notebooks and ~30 sample apps demonstrating individual Vertex AI / Gemini capabilities. Rough inventory:

| Metric | Count |
|---|---|
| Jupyter notebooks | 332 |
| Python files | 459 |
| `requirements.txt` files | 46 (no shared dependency management) |
| `pyproject.toml` files | 22 |
| Dockerfiles | 42 |
| Test files (`test_*.py`) | 27, concentrated in ~5 sample apps |
| README files | 118 |
| Total size | ~228 MB (large binary/notebook assets: audio, video, images) |

Top-level domains: `gemini/` (190 MB — getting-started, function-calling, evaluation, rag-engine, agents, multimodal-live-api, sample-apps, etc.), `agents/` (ADK agents, Agent Engine, Cloud Run agents, agent swarms), `embeddings/`, `search/` (Vertex AI Search / Agent Builder), `open-models/`, `vision/`, `audio/`, `translation/`, `partner-models/claude`, `tools/llmevalkit`, `rag-grounding/`.

CI today is a single `linter.yaml` (Super Linter, formatting-only across mixed languages), plus a link-checker and an issue-assigner bot — no test execution, no security scanning, no build/deploy pipeline at the top level. Individual sample apps have their own ad hoc CI/CD or none.

**Conclusion:** everything here is example/reference material, correctly licensed to Google (Apache 2.0, per `LICENSE`) and clearly authored by Google engineers and contributors (see `CONTRIBUTING.md`, individual notebook headers). None of it can be presented as originally written by me. What I can legitimately claim is: *engineering work that selects, adapts, hardens, tests, documents, and assembles a subset of this reference material into an original, working platform, clearly attributing the base material.*

---

## 2. Reusable building blocks (by capability)

| Capability | Best reusable reference | Reuse verdict |
|---|---|---|
| Gemini basics / config (temperature, safety settings, structured output) | `gemini/getting-started/`, `gemini/controlled-generation/` | Reuse as **pattern reference only** — needs wrapping in a real config-driven adapter (Phase 3). |
| Function/tool calling | `gemini/function-calling/intro_function_calling.ipynb`, `forced_function_calling.ipynb`, `parallel_function_calling.ipynb` | Good patterns for tool-schema design; not production code (no validation, no error handling, no loop limits). |
| RAG / retrieval | `gemini/rag-engine/*` (Vertex AI RAG Engine, Vector Search, Vertex AI Search, feature store, Pinecone/Weaviate variants), `embeddings/intro-textemb-vectorsearch.ipynb`, `embeddings/hybrid-search.ipynb`, `rag-grounding/` | Nine near-duplicate "intro to RAG with vector store X" notebooks. Confirms Vertex AI offers **three overlapping retrieval paths** (RAG Engine managed corpus, raw Vector Search, Vertex AI Search) — a real architecture decision needs to be made and documented (Phase 4), not all three implemented. |
| Agents | `agents/adk/*` (many ADK sample agents — e.g. `new-hire-onboarding`, `agent-quality-flywheel`, `contract-compliance-pipeline`), `agents/agent_engine`, `agents/cloud_run`, `agents/managed-agents`, `gemini/sample-apps/rosetta-agent-porter`, `gemini/sample-apps/swot-agent` | Best production-shaped reference in the whole repo is `rosetta-agent-porter`: has `app/` package, `tests/unit` + `tests/integration`, `deployment/cloudbuild.yaml`, `pyproject.toml`, `.env.example`, `Makefile`. This is the closest thing to a template worth following for structure (not for content — it solves an unrelated problem, code porting). |
| Evaluation | `gemini/evaluation/*` (~19 notebooks: Gen AI Eval SDK, agent-as-judge, ADK agent evaluation, structured-output evaluation) | Real Vertex AI Gen AI Evaluation Service exists and is scriptable outside notebooks — reusable as the backbone for Phase 9, but every notebook here is exploratory, not a repeatable pipeline. |
| Multimodal | `embeddings/intro_multimodal_embeddings.ipynb`, `gemini/getting-started` multimodal examples, `vision/` | Fine as a reference for the extraction pattern (Phase 6); needs a real use case wired to validation, not left as a standalone demo. |
| Deployment | `gemini/sample-apps/gemini-streamlit-cloudrun`, `gemini-quart-cloudrun`, `rosetta-agent-porter/Dockerfile` + `deployment/cloudbuild.yaml` | Legitimate minimal Cloud Run patterns (Dockerfile + `app.py`), but none show health/readiness endpoints, secret injection via Secret Manager, or IAM-scoped service accounts. |
| The former flagship starter | `gemini/sample-apps/e2e-gen-ai-app-starter-pack/` | **Dead** — it's a stub README pointing to `GoogleCloudPlatform/agent-starter-pack`, the actual maintained production starter template now lives in a separate repo. Not present in this zip; can reference its documented architecture but cannot copy its code (not in this repo). |
| Security | `SECURITY.md` (top-level, generic Google vulnerability-disclosure policy) | Not application security guidance — irrelevant to what Phase 13 needs. |

---

## 3. Findings by severity

### CRITICAL
1. **No coherent application exists anywhere in the repo.** Every capability lives in an isolated notebook or a self-contained toy sample app. There is no single system where ingestion → retrieval → generation → citation → evaluation → monitoring are wired together end to end. Building this is the actual work of Phases 2–19, not an adaptation exercise.
2. **No automated test suite at the platform level.** 27 test files exist across ~30 sample apps; most sample apps (including the popular `gemini-streamlit-cloudrun`, `gemini-quart-cloudrun`) have zero tests.
3. **No security engineering anywhere applicable to an app I'd own.** The repo's `SECURITY.md` is Google's own disclosure policy, not usable content. No example demonstrates prompt-injection defense, tool-authorization, upload validation, or Secret Manager usage together in one place.
4. **No CI beyond linting.** No test execution, no dependency/security scanning (no CodeQL/Dependabot config found), no Docker build validation, no deploy pipeline at the top level.

### HIGH
5. **Retrieval architecture ambiguity.** Nine overlapping "how to do RAG" notebooks (RAG Engine managed corpus, raw Vertex AI Vector Search, Vertex AI Search/Agent Builder, plus third-party Pinecone/Weaviate variants) exist with no guidance on when to use which. A real decision + write-up is required (Phase 4), not a reuse of all of them.
6. **No evaluation pipeline, only exploratory notebooks.** ~19 evaluation notebooks show *how the Vertex AI Gen AI Evaluation Service works* but none produce a versioned, re-runnable evaluation report with tracked metrics over time.
7. **No agent safety controls demonstrated together.** Tool-calling notebooks show mechanics only; no example combines iteration limits, tool timeouts, tool authorization, and structured-output validation in one agent loop.
8. **Dependency sprawl.** 46 separate `requirements.txt` + 22 `pyproject.toml`, no lockfile discipline outside a few apps (only `rosetta-agent-porter` has a `uv.lock`). A new platform needs its own clean, pinned dependency set rather than inheriting any of these.

### MEDIUM
9. **Deployment examples are minimal Cloud Run demos, not production configs** — no documented IAM least-privilege service account, no Secret Manager wiring, no readiness/liveness distinction, no rollback story.
10. **No observability pattern anywhere** (no structured logging with correlation IDs, no Cloud Monitoring custom metrics, no cost/token tracking) across any sample app inspected.
11. **No cost-tracking or budget-guardrail example** anywhere in the repo despite dozens of apps that call paid Gemini/embedding endpoints.

### LOW
12. Notebook-first format is fine for Google's teaching purpose but is actively bad for a resume portfolio piece — a reviewer expects an importable package, not a notebook to step through.
13. Docs are scattered — 118 READMEs, no single narrative arc a reviewer can follow.

### IMPROVEMENT (portfolio-specific, not repo defects)
14. `rosetta-agent-porter`'s directory shape (`app/`, `tests/unit`, `tests/integration`, `deployment/`, `pyproject.toml`, `Makefile`, `.env.example`) is the one structure in this repo worth imitating for the new platform's layout — not its content.
15. Given three prior projects already cover Azure chatbot, AWS Bedrock RAG, and a full-stack RAG app (MediQuery), this GCP project's differentiation should lean hardest on **Agentic AI + evaluation + MLOps**, since that's the thinnest coverage in the other three per the brief — and it's also the area with the weakest working examples in this repo, so it needs the most original engineering.

---

## 4. Environment constraint that affects every later phase (read before Phase 2)

This matters enough to flag now rather than discover later: **the environment I'm building in has no network access and no GCP credentials.** Concretely, that means I can:

- Write all application code, an adapter layer, RAG pipeline, agent, tests (with mocked Vertex AI/Cloud clients), CI config, IaC, and documentation.
- Run unit/integration tests that mock Google Cloud SDKs, lint, type-check, and validate Docker builds *structurally* (I cannot pull base images without network, so `docker build` itself will not run here either — I can validate the Dockerfile syntactically and document the exact build/run commands).

I cannot:
- Call live Gemini/Vertex AI endpoints, generate real evaluation numbers, provision Vertex AI Vector Search, deploy to Cloud Run, or produce real latency/cost/traffic metrics.

Per the critical rules in the brief (no fabricated benchmarks, no fabricated deployment, no fabricated metrics), every doc I produce (`AI_EVALUATION.md`, `DEPLOYMENT.md`, `FINAL_AUDIT.md`, etc.) will explicitly mark evaluation numbers and deployment status as **"not yet run against live GCP resources — commands provided for you to run and record real results"** rather than inventing numbers. You'll need a real GCP project, billing enabled, and to run the eval/deploy commands yourself to get genuine metrics you can cite on a resume. I'll make that as close to one-command-easy as possible.

---

## 5. Recommended flagship shape (for Phase 2 discussion)

Given the audit, the flagship app that best fits the resume positioning and avoids duplicating your Azure/AWS/MediQuery projects:

- **Backend:** Python (FastAPI) service — `Application AI Service → Vertex AI Adapter → Gemini`, config-driven models.
- **RAG:** Cloud Storage ingestion → chunking → Vertex AI text-embedding model → **Vertex AI Vector Search** for retrieval (justified over RAG Engine's managed corpus for showing you understand the lower-level primitives, and over Vertex AI Search since that's a black-box product, not something you engineered) — decision written up in `RAG_DESIGN.md`.
- **Agentic layer:** a small tool-calling agent (RAG search tool + one structured/API tool, e.g. BigQuery or calculator) with strict schemas, iteration caps, and timeouts — modeled structurally on `rosetta-agent-porter`'s layout, not its code.
- **Frontend:** minimal React or Streamlit chat UI with citations and streaming — kept intentionally simple so review time goes to the backend engineering.
- **Structure:** `app/` (backend+agent), `frontend/`, `evaluation/`, `infra/` (Terraform or gcloud scripts), `tests/`, `docs/`.

I'd rather confirm a few decisions with you before generating hundreds of files, since they shape everything downstream.

---
*End of Phase 1 audit. No repository files besides this one were modified.*
