# AI_EVALUATION.md

## Status summary (read this first)

Numbers in this document come from one of two sources, and each number is
labeled with which:

- **`[SANDBOX-STDLIB]`** — computed in the environment that built this
  repository, using a standalone stdlib-only reimplementation of the exact
  same algorithms as the real code
  (`evaluation/_sandbox_verification_run.py`), because that environment had
  no network access to install FastAPI/Pydantic and therefore could not run
  the real application or harness. Raw output: `evaluation/results/sandbox_verification_run.json`.
- **`[REAL-HARNESS]`** — would come from actually running
  `evaluation/run_evaluation.py` (`make evaluate`) against the real
  application. **No numbers in this document currently carry this label —
  that command has not been run yet in any environment with the
  dependencies installed.** Run it and replace this section with the
  real output before citing these numbers anywhere more permanent than
  this repo.
- **No number here comes from live Vertex AI / Gemini.** Every number
  below reflects the deterministic local mock AI backend
  (`app/services/ai/local_backend.py`), not real model quality. See
  `AUDIT.md` §4 and `DEPLOYMENT.md` for what it would take to evaluate
  against live Gemini.

## Dataset

`evaluation/datasets/rag_eval_set.json` — 4 short documents, 5 RAG queries
(4 with a known-relevant document, 1 deliberately out-of-corpus), and 2
agent tool-selection queries. Intentionally small: the goal is a dataset a
reviewer can read end to end in the interview, not a benchmark-sized corpus.

## Metrics implemented (`evaluation/metrics.py`)

| Metric | Definition | Implemented |
|---|---|---|
| Precision@k | Fraction of top-k retrieved docs that are relevant | Yes |
| Recall@k | Fraction of known-relevant docs found in top-k | Yes |
| Answer relevance | Fraction of expected keywords present in the answer (a transparent proxy, not a judge-model score — see Limitations) | Yes |
| Groundedness | 1.0 iff the grounded/ungrounded decision matches expectation and a grounded answer actually carries ≥1 citation | Yes |
| Citation correctness | Fraction of cited documents that are in the known-relevant set | Yes |
| Retrieval/generation latency | Wall-clock time around the retrieval and generation calls | Yes (locally measurable; not representative of live Gemini latency) |
| Agent tool-selection accuracy | Whether the agent invoked the expected tool for a query | Yes |
| Token usage / estimated cost | Tracked per-call in `GenerationResult`/`EmbeddingResult` (`input_tokens`, `output_tokens`) | Fields exist; not aggregated into a report yet — see Limitations |

## `[SANDBOX-STDLIB]` measured results

```json
{
  "mean_precision_at_k": 0.6,
  "mean_recall_at_k": 0.8,
  "mean_relevance_keyword_score": 0.9,
  "groundedness_accuracy": 0.8,
  "mean_citation_correctness": 0.6,
  "mean_retrieval_latency_ms": 0.67,
  "agent_tool_selection_accuracy": 1.0
}
```

Full per-case breakdown: `evaluation/results/sandbox_verification_run.json`.

### The interesting result: a genuine, measured failure

Case `q5_out_of_corpus` ("What is the capital of France?", which has no
relevant document in the 4-document corpus) was **incorrectly grounded**:
the mock embedding gave it a top similarity of 0.2243 against an unrelated
document — higher than case `q1`'s genuine match (0.2077) — so it passed
the 0.15 similarity threshold and produced a false citation.

This is not a bug being swept under the rug: it's a real, reproducible
finding about the **deterministic hashed bag-of-tokens mock embedding**
(`app/services/ai/local_backend.py`), which has no real semantic
understanding — it hashes individual tokens into a fixed-size vector, so
short texts sharing even a few common tokens (or just colliding by hash)
can score deceptively high. A trained embedding model like
`text-embedding-005` encodes meaning, not token identity, and is expected
to correctly separate this case — but that has **not been verified**,
because no GCP access is available in this environment. Re-running
`make evaluate` with `GCP_USE_LIVE_VERTEX_AI=true` against real credentials
is the next concrete step to confirm that.

This is exactly why `RAG_DESIGN.md` flags the 0.15 threshold as
mock-backend-specific and not a production value.

## Methodology

1. Seed an in-memory vector store with the eval corpus using the same
   `Chunk`/embedding code path the real ingestion pipeline uses (bypassing
   only PDF/DOCX extraction, since the corpus is already plain text).
2. Run each query through the real `RagPipeline.answer()` (or the real
   `Agent.run()` for tool-selection cases) — the same code the API serves.
3. Compare retrieved/cited document IDs and the generated answer against
   the dataset's hand-labeled expectations using `evaluation/metrics.py`.
4. Aggregate into a summary and write both per-case and summary JSON to
   `evaluation/results/`.

Run it yourself:

```bash
make install
make evaluate
```

## Limitations

- **No live-model numbers.** Every result reflects the mock backend. This
  document will be updated with a clearly separate `[LIVE-VERTEX-AI]`
  section once that's been run against a real GCP project — it is not
  fabricated here.
- **Relevance is a keyword proxy**, not semantic judgment. A real
  deployment should additionally run Vertex AI's Gen AI Evaluation Service
  model-based relevance/coherence metrics (`gemini/evaluation/` in the
  base repo shows the SDK calls) — not implemented here to avoid another
  paid model call this environment can't make anyway.
- **Tiny dataset.** 5 RAG cases and 2 agent cases is enough to validate the
  metric *implementations* and catch the kind of calibration bug found
  above, not enough to make a statistically meaningful quality claim.
  Growing the dataset is the top priority before citing these numbers
  anywhere beyond this repo.
- **The 2 agent cases only cover `calculator` vs. `rag_search` tool
  selection — neither MCP tool (`mcp_text_stats`, `mcp_current_datetime`,
  added in a later pass; see `docs/MCP.md`) has an eval case yet.** MCP's
  own verification is separate and stdlib-only
  (`evaluation/_mcp_sandbox_verification.py`, `docs/MCP.md`
  "Verification status") and does not measure tool-*selection* accuracy
  the way this dataset does — it verifies the transport/execution
  mechanics, not whether the model reliably picks the MCP tool over
  another one. Extending `agent_cases` with MCP scenarios is a natural
  next step, not done here to keep this pass scoped to what was asked.
- **Token usage / cost is not yet aggregated** into the evaluation report,
  though every generation/embedding call already returns token counts —
  wiring that into `EvaluationReport` is a small follow-up.
- **No hallucination-specific metric beyond groundedness-as-defined.** A
  more rigorous approach (e.g. NLI-based entailment checking of the answer
  against retrieved context) is listed as future work, not implemented.
