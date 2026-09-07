"""Real evaluation harness: seeds the actual in-memory vector store via the
actual RagPipeline/Agent objects (same code the API uses) and computes the
metrics in evaluation/metrics.py.

STATUS: this module has NOT been executed in the sandbox that produced this
codebase — it imports FastAPI/Pydantic-dependent application code, and this
environment has no network access to install those dependencies. Run:

    make install
    make evaluate

to actually execute it against the local mock backend (no GCP credentials
needed — GCP_USE_LIVE_VERTEX_AI defaults to false), or set
GCP_USE_LIVE_VERTEX_AI=true with real credentials to evaluate against live
Gemini + Vertex AI Vector Search. See evaluation/results/ for the most
recent run's output, and AI_EVALUATION.md for the numbers currently on
record and how they were produced (including the stdlib-only sandbox
verification run used when this harness itself couldn't be executed).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from app.core.config import get_settings
from app.schemas.documents import Chunk
from app.services.agent.agent import Agent
from app.services.agent.tools.base import ToolRegistry
from app.services.agent.tools.calculator_tool import CalculatorTool
from app.services.agent.tools.rag_tool import RagSearchTool
from app.services.ai.service import build_ai_service
from app.services.rag.pipeline import RagPipeline
from app.services.storage.vector_store import InMemoryVectorStore
from evaluation.dataset import load_dataset
from evaluation.metrics import (
    CaseResult,
    EvaluationReport,
    citation_correctness,
    groundedness_score,
    keyword_relevance_score,
    precision_at_k,
    recall_at_k,
)


def run() -> EvaluationReport:
    settings = get_settings()
    ai_service = build_ai_service(settings)
    vector_store = InMemoryVectorStore()

    dataset = load_dataset()

    # Seed the corpus (bypassing full ingestion pipeline since the eval
    # dataset is already plain text — no PDF/DOCX extraction needed).
    chunks = [
        Chunk(document_id=d.document_id, filename=d.filename, text=d.text, source=d.filename)
        for d in dataset.corpus
    ]
    vectors = [ai_service.embed_texts([c.text]).vectors[0] for c in chunks]
    vector_store.upsert(chunks, vectors)

    rag_pipeline = RagPipeline(ai_service=ai_service, vector_store=vector_store, settings=settings)

    report = EvaluationReport(dataset_name=dataset.name)
    for case in dataset.rag_cases:
        t0 = time.perf_counter()
        response = rag_pipeline.answer(case.query)
        total_latency_ms = (time.perf_counter() - t0) * 1000

        retrieved_document_ids = [c.document_id for c in response.citations]
        cited_document_ids = [c.document_id for c in response.citations]

        result = CaseResult(
            case_id=case.case_id,
            precision_at_k=precision_at_k(retrieved_document_ids, case.relevant_document_ids, k=8),
            recall_at_k=recall_at_k(retrieved_document_ids, case.relevant_document_ids, k=8),
            relevance=keyword_relevance_score(response.answer, case.expected_keywords),
            groundedness=groundedness_score(
                citations_count=len(response.citations),
                grounded_flag=response.grounded,
                expected_grounded=case.expect_grounded,
            ),
            citation_correctness=citation_correctness(
                cited_document_ids, case.relevant_document_ids
            ),
            retrieval_latency_ms=total_latency_ms,  # combined retrieval+generation; see note below
            generation_latency_ms=response.latency_ms,
        )
        report.case_results.append(result)

    # Agent tool-selection cases.
    tool_registry = ToolRegistry(
        tools=[RagSearchTool(ai_service, vector_store, settings.retrieval), CalculatorTool()]
    )
    agent = Agent(ai_service, tool_registry, settings.agent)
    agent_correct = 0
    for case in dataset.agent_cases:
        response = agent.run(case.query)
        used_tools = {s.tool_call.tool.value for s in response.steps if s.tool_call}
        if case.expected_tool in used_tools:
            agent_correct += 1

    summary = report.summary()
    summary["agent_tool_selection_accuracy"] = (
        agent_correct / len(dataset.agent_cases) if dataset.agent_cases else None
    )

    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)
    out_path = results_dir / "latest_run.json"
    out_path.write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))
    return report


if __name__ == "__main__":
    run()
