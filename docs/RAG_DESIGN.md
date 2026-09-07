# RAG_DESIGN.md

## Chunking strategy

Paragraph-aware fixed-size windows with overlap (`app/services/rag/chunking.py`):
split on blank lines first, accumulate paragraphs up to `chunk_size_tokens`
(default 400, whitespace-token approximation, not a real tokenizer — see
Limitations), then start the next chunk with the last `chunk_overlap_tokens`
(default 60) words carried forward before adding new content. A paragraph
longer than the chunk size is hard-split with the same overlap. This avoids
a tokenizer dependency purely for chunk boundaries; the embedding model's
own tokenizer is the ground truth at embedding time regardless, and the
60-token overlap absorbs boundary information loss (e.g. a sentence that
would otherwise be cut in half is very likely to appear whole in one of the
two adjacent chunks).

## Embedding model

Configured as `text-embedding-005` (Vertex AI's current general-purpose
text embedding model) via `EMBED_MODEL_NAME`, at 768 output dimensions.
Chosen over the multimodal embedding model because the flagship use case is
text-document RAG; if the multimodal phase (Phase 6) later needs to embed
images directly rather than extracted text, that would use a separate,
explicitly-named multimodal embedding call rather than silently changing
this one.

**This has not been exercised against the real model in this environment**
(no GCP credentials/network here). The application ships a deterministic
local mock embedding (`app/services/ai/local_backend.py`) — a hashed
bag-of-tokens vector — used whenever `GCP_USE_LIVE_VERTEX_AI=false`, so the
RAG pipeline, chunking, retrieval ranking, and citation logic are all fully
exercised end to end without it. Its purpose is to make the *control flow*
testable, not to demonstrate embedding quality.

## Vector storage: decision and alternatives considered

Three Vertex AI retrieval paths exist and were evaluated (see `AUDIT.md`
§2):

| Option | Verdict |
|---|---|
| **Vertex AI RAG Engine** (managed corpus) | Fastest to stand up, but it owns chunking/retrieval internally — there is very little retrieval engineering left to build or defend in an interview. Rejected for the flagship path for that reason (still worth knowing about; mentioned in `INTERVIEW_GUIDE.md`). |
| **Vertex AI Search / Agent Builder** | A packaged enterprise search product, not a primitive you engineer against — same objection as above, plus it pulls in a separate data-store/indexing config surface unrelated to the rest of this codebase. |
| **Vertex AI Vector Search** (chosen) | Lowest-level primitive that still demonstrates real engineering: you build the index, choose the distance metric, manage upserts/deletes, and own the metadata-filtering and similarity-threshold logic yourself. This is what `app/services/storage/vector_store.py`'s `VertexVectorSearchStore` implements. |

Chosen: **Vertex AI Vector Search**, behind the same `VectorStore` interface
implemented locally by `InMemoryVectorStore` (linear scan, used whenever
`GCP_USE_LIVE_VERTEX_AI=false`). Swapping backends is a one-line config
change (`app/dependencies.py::get_vector_store`), not a rewrite.

**Deployment status:** `VertexVectorSearchStore` is real, runnable code
against `google-cloud-aiplatform`, but no index or endpoint has actually
been created or queried in a live GCP project from this environment — see
`DEPLOYMENT.md` for the exact `gcloud`/Terraform steps to do that yourself.

## Similarity scoring — a real calibration issue, and how it was found

Cosine similarity is computed in `app/services/storage/vector_store.py`.
Two approaches were tried while building this:

1. **Rescale `cos ∈ [-1,1]` to `[0,1]` via `(cos+1)/2`.** Rejected after
   measurement: for the sparse hashed vectors the local mock backend
   produces, unrelated text pairs have a raw cosine near 0, which the
   rescaling maps to **0.5** — uncomfortably close to any reasonable
   threshold, making the threshold nearly meaningless for the mock backend.
2. **Raw cosine, clipped to `[0, ∞) → [0, 1]` via `max(cos, 0)`.** Adopted.
   Unrelated pairs score near 0, related pairs score meaningfully higher.

`RETRIEVAL_SIMILARITY_THRESHOLD` defaults to **0.15**, calibrated against
the local mock backend's score distribution (see `AI_EVALUATION.md` for the
actual measured scores). **This number does not transfer to a real
embedding model.** Trained embeddings from `text-embedding-005` cluster far
more tightly and are far better separated between related/unrelated text;
using 0.15 against real embeddings would likely retrieve almost everything.
Re-tune this threshold by running the evaluation harness (`make evaluate`)
against live Vertex AI before any real deployment.

## Retrieval quality techniques (Phase 5) — implemented vs. skipped

**Implemented**, in `app/services/rag/retrieval.py`:
- **Top-k retrieval** from the vector store (`RETRIEVAL_TOP_K`, default 8).
- **Similarity-threshold filtering** — chunks below the floor are dropped
  rather than always forcing `top_k` results into the prompt.
- **Deduplication** — chunks whose Jaccard word-overlap exceeds
  `RETRIEVAL_DEDUPE_SIMILARITY_THRESHOLD` (default 0.97) are collapsed,
  since overlapping chunk windows or repeated boilerplate across documents
  commonly produce near-duplicates.
- **Context-size capping** (`RETRIEVAL_MAX_CONTEXT_CHUNKS`, default 5) —
  bounds prompt size and cost regardless of how many chunks pass threshold.

**Deliberately not implemented**, to avoid unjustified complexity (Phase 5
explicitly warns against over-engineering):
- **Query rewriting.** Would help with very short or ambiguous queries, but
  adds an extra model call (cost + latency) on every request. Worth adding
  if evaluation on a larger, real dataset shows queries frequently miss due
  to vocabulary mismatch — not yet demonstrated.
- **Reranking (e.g. a cross-encoder or Vertex AI Ranking API pass).** Real
  value only shows up once `top_k` retrieval reliably returns a reasonably
  sized relevant candidate set to rerank; with the current small demo
  corpus there's nothing to meaningfully rerank. Documented here as the
  first thing to add if evaluation on a larger real corpus shows precision
  problems within the already-retrieved set.

## Metadata and provenance

Every `Chunk` (`app/schemas/documents.py`) carries `document_id`,
`filename`, `page` (nullable — only PDFs have real page numbers), `chunk_id`,
`source` (local path or `gs://...` URI), `created_at`, and `tenant_id`
(nullable, used for retrieval scoping). Every `Citation` returned by
`/chat` is built directly from this metadata (`citations_from_chunks` in
`app/schemas/chat.py`), so a citation can always be traced back to the
exact chunk and source document that produced it.

## Limitations

- Chunk sizing uses whitespace-token counts as a token-count approximation,
  not the real embedding model's tokenizer — sizes will be somewhat off
  (typically chunks will contain slightly more real tokens than the
  configured word count, since sub-word tokenization usually produces more
  tokens than whitespace splitting).
- The in-memory vector store is an O(n) linear scan — fine for this
  portfolio's demo corpus and test suite, not a substitute for Vector
  Search's ANN index at real scale.
- The 0.15 similarity threshold is a mock-backend calibration, not a
  production-ready value (see above and `AI_EVALUATION.md`).
- No query rewriting or reranking (see above) — explicitly deferred, not
  an oversight.
- Tenant isolation is enforced by a `tenant_id` filter at query time, not
  by separate physical indexes per tenant — acceptable for this portfolio
  scale, and called out as a scaling/isolation tradeoff in `SECURITY.md`.
