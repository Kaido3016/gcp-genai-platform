"""Integration tests for the bounded agent loop using the local mock AI
backend (Phase 7)."""

from app.core.config import AgentConfig
from app.schemas.agent import AgentStepKind
from app.services.agent.agent import Agent


def test_agent_uses_calculator_tool_for_math_query(agent):
    response = agent.run("What is 12 + 30?")
    assert response.stopped_reason == "final_answer"
    tool_call_steps = [s for s in response.steps if s.kind == AgentStepKind.TOOL_CALL]
    assert any(s.tool_call.tool.value == "calculator" for s in tool_call_steps)
    assert response.iterations_used <= 6


def test_agent_uses_rag_tool_for_document_query(agent, vector_store, ai_service):
    from app.schemas.documents import Chunk

    chunk = Chunk(document_id="d1", filename="policy.txt", text="Refunds are processed within 5 business days.", source="policy.txt")
    vector = ai_service.embed_texts([chunk.text]).vectors[0]
    vector_store.upsert([chunk], [vector])

    response = agent.run("What does the refund policy say?")
    tool_call_steps = [s for s in response.steps if s.kind == AgentStepKind.TOOL_CALL]
    assert any(s.tool_call.tool.value == "rag_search" for s in tool_call_steps)
    assert response.stopped_reason == "final_answer"


def test_agent_respects_max_iterations(ai_service, tool_registry):
    """A tiny iteration budget must stop the loop deterministically rather
    than looping forever, even if the model keeps requesting tools."""
    tiny_config = AgentConfig(max_iterations=1, tool_timeout_seconds=5, max_tool_calls_per_turn=8)
    agent = Agent(ai_service, tool_registry, tiny_config)

    response = agent.run("What is 5 * 5?")
    assert response.iterations_used <= 1
    assert response.stopped_reason in ("max_iterations", "final_answer")


def test_agent_records_full_step_trace(agent):
    response = agent.run("What is 7 + 8?")
    kinds = [s.kind for s in response.steps]
    assert AgentStepKind.TOOL_CALL in kinds
    assert AgentStepKind.TOOL_RESULT in kinds
    assert AgentStepKind.FINAL_ANSWER in kinds


def test_agent_final_answer_uses_tool_result(agent):
    response = agent.run("What is 4 * 4?")
    tool_results = [s for s in response.steps if s.kind == AgentStepKind.TOOL_RESULT]
    assert tool_results
    assert tool_results[0].tool_result.success is True
    assert tool_results[0].tool_result.output["result"] == 16.0
