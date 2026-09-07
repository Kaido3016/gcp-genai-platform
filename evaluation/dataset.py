"""Loads the reproducible eval dataset from evaluation/datasets/."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DATASET_PATH = Path(__file__).parent / "datasets" / "rag_eval_set.json"


@dataclass
class CorpusDoc:
    document_id: str
    filename: str
    text: str


@dataclass
class RagCase:
    case_id: str
    query: str
    relevant_document_ids: set[str]
    expected_keywords: list[str]
    expect_grounded: bool


@dataclass
class AgentCase:
    case_id: str
    query: str
    expected_tool: str


@dataclass
class EvalDataset:
    name: str
    corpus: list[CorpusDoc]
    rag_cases: list[RagCase]
    agent_cases: list[AgentCase]


def load_dataset(path: Path = DATASET_PATH) -> EvalDataset:
    raw = json.loads(path.read_text())
    corpus = [CorpusDoc(**d) for d in raw["corpus"]]
    rag_cases = [
        RagCase(
            case_id=c["case_id"],
            query=c["query"],
            relevant_document_ids=set(c["relevant_document_ids"]),
            expected_keywords=c["expected_keywords"],
            expect_grounded=c["expect_grounded"],
        )
        for c in raw["cases"]
    ]
    agent_cases = [AgentCase(**c) for c in raw.get("agent_cases", [])]
    return EvalDataset(
        name=raw["dataset_name"], corpus=corpus, rag_cases=rag_cases, agent_cases=agent_cases
    )
