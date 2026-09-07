"""Evaluation metric implementations.

Deliberately dependency-light (stdlib only, no pydantic/app imports) so
these functions can be unit tested and even sanity-checked in environments
where the full app dependency stack isn't installed. `run_evaluation.py`
imports these and wires them to the real RAG pipeline / agent.
"""

from __future__ import annotations

from dataclasses import dataclass, field


def precision_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """Fraction of the top-k retrieved chunk/document IDs that are relevant."""
    top_k = retrieved_ids[:k]
    if not top_k:
        return 0.0
    hits = sum(1 for rid in top_k if rid in relevant_ids)
    return hits / len(top_k)


def recall_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """Fraction of all known-relevant IDs that appear in the top-k retrieved."""
    if not relevant_ids:
        return 1.0 if not retrieved_ids[:k] else 0.0
    top_k = set(retrieved_ids[:k])
    hits = len(top_k & relevant_ids)
    return hits / len(relevant_ids)


def keyword_relevance_score(answer: str, expected_keywords: list[str]) -> float:
    """Cheap, transparent proxy for "answer relevance" that doesn't require
    a judge model: fraction of expected keywords/phrases present in the
    answer (case-insensitive substring match). This is intentionally
    simple and documented as a proxy, not a claim of semantic evaluation
    (see AI_EVALUATION.md limitations) — a real deployment should also run
    Vertex AI Gen AI Evaluation Service's model-based relevance metric.
    """
    if not expected_keywords:
        return 1.0
    answer_lower = answer.lower()
    hits = sum(1 for kw in expected_keywords if kw.lower() in answer_lower)
    return hits / len(expected_keywords)


def groundedness_score(citations_count: int, grounded_flag: bool, expected_grounded: bool) -> float:
    """1.0 if the grounded/ungrounded decision matches expectation AND (when
    grounded) at least one citation was actually returned; 0.0 otherwise.
    Catches the specific hallucination-risk failure mode of an answer
    claiming to be grounded with zero supporting citations.
    """
    if grounded_flag != expected_grounded:
        return 0.0
    if grounded_flag and citations_count == 0:
        return 0.0
    return 1.0


def citation_correctness(cited_document_ids: list[str], relevant_document_ids: set[str]) -> float:
    """Fraction of cited documents that are actually in the known-relevant
    set for this query — catches citations pointing at the wrong source."""
    if not cited_document_ids:
        return 0.0
    correct = sum(1 for d in cited_document_ids if d in relevant_document_ids)
    return correct / len(cited_document_ids)


@dataclass
class CaseResult:
    case_id: str
    precision_at_k: float
    recall_at_k: float
    relevance: float
    groundedness: float
    citation_correctness: float
    retrieval_latency_ms: float
    generation_latency_ms: float
    tool_selection_correct: bool | None = None
    notes: str = ""


@dataclass
class EvaluationReport:
    dataset_name: str
    case_results: list[CaseResult] = field(default_factory=list)

    def summary(self) -> dict:
        n = len(self.case_results) or 1
        return {
            "dataset_name": self.dataset_name,
            "case_count": len(self.case_results),
            "mean_precision_at_k": sum(c.precision_at_k for c in self.case_results) / n,
            "mean_recall_at_k": sum(c.recall_at_k for c in self.case_results) / n,
            "mean_relevance": sum(c.relevance for c in self.case_results) / n,
            "mean_groundedness": sum(c.groundedness for c in self.case_results) / n,
            "mean_citation_correctness": sum(c.citation_correctness for c in self.case_results) / n,
            "mean_retrieval_latency_ms": sum(c.retrieval_latency_ms for c in self.case_results) / n,
            "mean_generation_latency_ms": sum(c.generation_latency_ms for c in self.case_results) / n,
            "tool_selection_accuracy": (
                sum(1 for c in self.case_results if c.tool_selection_correct) / n
                if any(c.tool_selection_correct is not None for c in self.case_results)
                else None
            ),
        }
