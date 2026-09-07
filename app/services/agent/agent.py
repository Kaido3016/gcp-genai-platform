"""Agent loop.

Understand -> select tool -> execute -> inspect result -> continue or
finish. Bounded by AgentConfig.max_iterations and per-tool timeout
(Phase 7). Every step is recorded in AgentResponse.steps for observability
and for the evaluation harness (Phase 9) to score tool-selection quality.
"""

from __future__ import annotations

import logging
import time
import uuid

from app.core.config import AgentConfig
from app.core.logging import get_logger, log_event
from app.schemas.agent import (
    AgentResponse,
    AgentStep,
    AgentStepKind,
    ToolCall,
    ToolName,
    ToolResult,
)
from app.services.agent.tools.base import ToolRegistry
from app.services.ai.base import AIService, ToolDeclaration

logger = get_logger(__name__)

SYSTEM_INSTRUCTION = (
    "You are an assistant that can use tools to answer questions accurately. "
    "Prefer using a tool over guessing when the question requires document "
    "lookup or arithmetic. Once you have enough information, give a final "
    "answer without calling further tools."
)


class Agent:
    def __init__(self, ai_service: AIService, tool_registry: ToolRegistry, config: AgentConfig):
        self._ai = ai_service
        self._tools = tool_registry
        self._config = config

    def run(self, query: str, *, tenant_id: str | None = None) -> AgentResponse:
        start = time.perf_counter()
        steps: list[AgentStep] = []
        history: list[dict] = []
        tool_declarations = [
            ToolDeclaration(
                name=t.name.value, description=t.description, parameters_schema=t.json_schema()
            )
            for t in self._tools.all()
        ]
        context = {"tenant_id": tenant_id, "is_privileged": False}

        model_used = "unknown"
        for iteration in range(1, self._config.max_iterations + 1):
            result = self._ai.generate_with_tools(
                query,
                tools=tool_declarations,
                system_instruction=SYSTEM_INSTRUCTION,
                history=history,
            )
            model_used = result.model

            if not result.tool_calls:
                answer = result.text or "No answer could be produced."
                steps.append(AgentStep(kind=AgentStepKind.FINAL_ANSWER, content=answer))
                log_event(
                    logger,
                    logging.INFO,
                    "agent_completed",
                    iterations=iteration,
                    stopped_reason="final_answer",
                    duration_ms=round((time.perf_counter() - start) * 1000, 1),
                )
                return AgentResponse(
                    answer=answer,
                    steps=steps,
                    iterations_used=iteration,
                    stopped_reason="final_answer",
                    model_used=model_used,
                    latency_ms=round((time.perf_counter() - start) * 1000, 1),
                )

            # Execute up to max_tool_calls_per_turn requested tool calls.
            for call in result.tool_calls[: self._config.max_tool_calls_per_turn]:
                call_id = str(uuid.uuid4())
                try:
                    tool_name = ToolName(call.name)
                except ValueError:
                    steps.append(
                        AgentStep(
                            kind=AgentStepKind.TOOL_RESULT,
                            content=f"Unknown tool requested: {call.name}",
                        )
                    )
                    continue
                tool_call = ToolCall(tool=tool_name, arguments=call.arguments, call_id=call_id)
                steps.append(
                    AgentStep(
                        kind=AgentStepKind.TOOL_CALL, content=tool_name.value, tool_call=tool_call
                    )
                )

                tool_result: ToolResult = self._tools.execute(
                    tool_name,
                    call.arguments,
                    call_id=call_id,
                    context=context,
                    timeout_seconds=self._config.tool_timeout_seconds,
                )
                steps.append(
                    AgentStep(
                        kind=AgentStepKind.TOOL_RESULT,
                        content=str(
                            tool_result.output if tool_result.success else tool_result.error
                        ),
                        tool_result=tool_result,
                    )
                )
                history.append(
                    {
                        "role": "tool_result",
                        "tool": tool_name.value,
                        "output": tool_result.output
                        if tool_result.success
                        else f"ERROR: {tool_result.error}",
                    }
                )

        # Iteration budget exhausted without a final answer.
        log_event(
            logger,
            logging.WARNING,
            "agent_max_iterations",
            iterations=self._config.max_iterations,
            duration_ms=round((time.perf_counter() - start) * 1000, 1),
        )
        fallback_answer = (
            "I wasn't able to reach a final answer within the allowed number "
            "of reasoning steps. Here is what I found so far: "
            + "; ".join(
                str(s.tool_result.output)
                for s in steps
                if s.kind == AgentStepKind.TOOL_RESULT and s.tool_result and s.tool_result.success
            )
        )
        return AgentResponse(
            answer=fallback_answer,
            steps=steps,
            iterations_used=self._config.max_iterations,
            stopped_reason="max_iterations",
            model_used=model_used,
            latency_ms=round((time.perf_counter() - start) * 1000, 1),
        )
