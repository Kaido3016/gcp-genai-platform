"""Standalone verification run — NOT part of the application.

This sandbox has no network access, so the real dependency stack could not
be installed to execute the actual FastAPI app in this session. This script
reimplements the evaluation algorithms using only the standard library.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

DIM = 768
SIMILARITY_THRESHOLD = 0.15
TOP_K = 8


def hash_embed(text: str, dim: int = DIM) -> list[float]:
    vec = [0.0] * dim
    for tok in re.findall(r"[a-z0-9]+", text.lower()):
        h = int(hashlib.sha256(tok.encode()).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h >> 1) % 2 == 0 else -1.0
        vec[idx] += sign
    norm = sum(v * v for v in vec) ** 0.5
    return [v / norm for v in vec] if norm else vec


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return max(dot / (na * nb), 0.0)


def precision_at_k(retrieved, relevant, k):
    top = retrieved[:k]
    if not top:
        return 0.0
    return sum(1 for r in top if r in relevant) / len(top)


def recall_at_k(retrieved, relevant, k):
    if not relevant:
        return 1.0 if not retrieved[:k] else 0.0
    top = set(retrieved[:k])
    return len(top & relevant) / len(relevant)


def keyword_relevance(answer: str, keywords: list[str]) -> float:
    if not keywords:
        return 1.0
    lower = answer.lower()
    return sum(1 for k in keywords if k.lower() in lower) / len(keywords)


def looks_like_math(text: str) -> bool:
    return bool(re.search(r"\d+\s*[\+\-\*/]\s*\d+", text.lower()))


def main() -> None:
    dataset_path = Path(__file__).parent / "datasets" / "rag_eval_set.json"
    data = json.loads(dataset_path.read_text())
    corpus = data["corpus"]
    corpus_vectors = {d["document_id"]: hash_embed(d["text"]) for d in corpus}

    case_reports = []
    for case in data["cases"]:
        t0 = time.perf_counter()
        qv = hash_embed(case["query"])
        scored = sorted(
            ((cosine(qv, corpus_vectors[d["document_id"]]), d["document_id"]) for d in corpus),
            reverse=True,
        )
        retrieval_latency_ms = (time.perf_counter() - t0) * 1000
        above_threshold = [
            doc_id for score, doc_id in scored if score >= SIMILARITY_THRESHOLD
        ][:TOP_K]

        relevant = set(case["relevant_document_ids"])
        grounded = len(above_threshold) > 0
        expect_grounded = case["expect_grounded"]

        if grounded:
            cited_text = " ".join(
                d["text"] for d in corpus if d["document_id"] in above_threshold
            )
            answer = f"Based on the retrieved context: {cited_text[:300]}"
        else:
            answer = "No supporting documents were found for this query."

        report = {
            "case_id": case["case_id"],
            "query": case["query"],
            "top_score": round(scored[0][0], 4),
            "precision_at_k": precision_at_k(above_threshold, relevant, TOP_K),
            "recall_at_k": recall_at_k(above_threshold, relevant, TOP_K),
            "relevance_keyword_score": keyword_relevance(answer, case["expected_keywords"]),
            "grounded": grounded,
            "expect_grounded": expect_grounded,
            "groundedness_correct": grounded == expect_grounded,
            "citation_correctness": (
                (sum(1 for d in above_threshold if d in relevant) / len(above_threshold))
                if above_threshold
                else (1.0 if not relevant else 0.0)
            ),
            "retrieval_latency_ms": round(retrieval_latency_ms, 4),
        }
        case_reports.append(report)

    agent_reports = []
    for case in data["agent_cases"]:
        predicted_tool = "calculator" if looks_like_math(case["query"]) else "rag_search"
        agent_reports.append(
            {
                "case_id": case["case_id"],
                "query": case["query"],
                "expected_tool": case["expected_tool"],
                "predicted_tool": predicted_tool,
                "correct": predicted_tool == case["expected_tool"],
            }
        )

    n = len(case_reports)
    summary = {
        "dataset_name": data["dataset_name"],
        "case_count": n,
        "mean_precision_at_k": round(sum(c["precision_at_k"] for c in case_reports) / n, 4),
        "mean_recall_at_k": round(sum(c["recall_at_k"] for c in case_reports) / n, 4),
        "mean_relevance_keyword_score": round(
            sum(c["relevance_keyword_score"] for c in case_reports) / n, 4
        ),
        "groundedness_accuracy": round(
            sum(1 for c in case_reports if c["groundedness_correct"]) / n, 4
        ),
        "mean_citation_correctness": round(
            sum(c["citation_correctness"] for c in case_reports) / n, 4
        ),
        "mean_retrieval_latency_ms": round(
            sum(c["retrieval_latency_ms"] for c in case_reports) / n, 4
        ),
        "agent_tool_selection_accuracy": round(
            sum(1 for a in agent_reports if a["correct"]) / len(agent_reports), 4
        ),
    }

    output = {"summary": summary, "cases": case_reports, "agent_cases": agent_reports}
    out_path = Path(__file__).parent / "results" / "sandbox_verification_run.json"
    out_path.write_text(json.dumps(output, indent=2))
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
