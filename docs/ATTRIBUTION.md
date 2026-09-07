# ATTRIBUTION.md

This project lives inside a clone of `GoogleCloudPlatform/generative-ai`
(Apache 2.0 licensed — see `../LICENSE`). This file draws a hard line
between what Google authored and what was engineered from scratch for
this portfolio project.

## From `GoogleCloudPlatform/generative-ai` (Google's work, not mine)

Nothing from the reference repository's notebooks or sample apps was
copied into `gcp-genai-platform/`. What was used from it:

- **Conceptual patterns only**, credited in `AUDIT.md` §2 and
  `RAG_DESIGN.md`: e.g. the existence of Vertex AI Vector Search vs. RAG
  Engine vs. Vertex AI Search as three retrieval options (seen across
  `gemini/rag-engine/*.ipynb`), the shape of a Gemini function-calling
  request (seen in `gemini/function-calling/*.ipynb`), and the directory
  layout of `gemini/sample-apps/rosetta-agent-porter` (an unrelated
  Google sample app whose `app/ + tests/unit + tests/integration +
  deployment/ + pyproject.toml` shape was used as a structural reference
  for how to organize a production-shaped Python package — none of its
  code was reused, it solves a completely different problem).
- **The official Vertex AI / `google-genai` / `google-cloud-aiplatform`
  SDK surface**, which any Google Cloud application necessarily calls —
  using a vendor's public SDK as intended is not a copyright concern and
  is not claimed as original work; only the application code built
  around those SDK calls (the adapter, retry logic, config layer, RAG
  pipeline, agent loop, API) is original.

No notebook cells, sample-app source files, or Google-authored prose were
copied, adapted line-by-line, or reformatted into this project. `AUDIT.md`
documents the full inventory of what exists in the reference repo and
explicitly states none of it is presented as personally authored.

## Original engineering work (this project)

Everything under `gcp-genai-platform/` — the FastAPI application, the
Vertex AI abstraction layer (`app/services/ai/`), the RAG pipeline
(`app/services/rag/`), the vector store and document store abstractions
(`app/services/storage/`), the agent loop and tool registry
(`app/services/agent/`), all Pydantic schemas, all tests, the evaluation
harness and dataset, the frontend, the CI/CD configuration, and every
document in `docs/` — was designed and written for this project. See
`FINAL_AUDIT.md` for exactly what was implemented, tested, and verified,
and what remains unverified pending a real GCP environment.

## License

This subdirectory is offered under the same Apache 2.0 license as the
surrounding repository (`../LICENSE`), consistent with building on top of
Google's Apache-2.0-licensed reference material.
