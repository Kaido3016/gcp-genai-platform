"""Tool protocol + registry.

Phase 7 safety controls implemented here:
- strict Pydantic argument validation before execution (ToolInputValidationError)
- per-tool authorization check (ToolAuthorizationError)
- execution timeout via a worker thread (ToolTimeoutError)
- no arbitrary code execution — tools are a fixed, explicit registry, never
  a generic "run this code" capability.
"""

from __future__ import annotations

import concurrent.futures
import time
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ValidationError

from app.core.exceptions import (
    ToolAuthorizationError,
    ToolExecutionError,
    ToolInputValidationError,
    ToolNotFoundError,
    ToolTimeoutError,
)
from app.schemas.agent import TOOL_ARG_SCHEMAS, ToolName, ToolResult


class Tool(ABC):
    name: ToolName
    description: str
    #: Tenants/roles allowed to use this tool. None means "all authenticated
    #: callers" — kept explicit so adding a privileged tool later forces a
    #: conscious authorization decision rather than defaulting open.
    allowed_for_all: bool = True

    @abstractmethod
    def run(self, args: BaseModel, *, context: dict[str, Any]) -> Any: ...

    def json_schema(self) -> dict:
        schema_cls = TOOL_ARG_SCHEMAS[self.name]
        return schema_cls.model_json_schema()


class ToolRegistry:
    def __init__(self, tools: list[Tool]):
        self._tools: dict[ToolName, Tool] = {t.name: t for t in tools}

    def get(self, name: ToolName) -> Tool:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolNotFoundError(f"Tool '{name}' is not registered.")
        return tool

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def execute(
        self,
        name: ToolName,
        raw_arguments: dict,
        *,
        call_id: str,
        context: dict[str, Any],
        timeout_seconds: float,
    ) -> ToolResult:
        start = time.perf_counter()
        try:
            tool = self.get(name)
        except ToolNotFoundError as exc:
            return ToolResult(call_id=call_id, tool=name, success=False, error=str(exc))

        if not tool.allowed_for_all and not context.get("is_privileged"):
            err = ToolAuthorizationError(f"Not authorized to use tool '{name}'.")
            return ToolResult(call_id=call_id, tool=name, success=False, error=str(err))

        schema_cls = TOOL_ARG_SCHEMAS[name]
        try:
            validated_args = schema_cls.model_validate(raw_arguments)
        except ValidationError as exc:
            err = ToolInputValidationError(str(exc))
            return ToolResult(call_id=call_id, tool=name, success=False, error=str(err))

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(tool.run, validated_args, context=context)
            try:
                output = future.result(timeout=timeout_seconds)
            except concurrent.futures.TimeoutError:
                err = ToolTimeoutError(f"Tool '{name}' exceeded {timeout_seconds}s timeout.")
                return ToolResult(
                    call_id=call_id,
                    tool=name,
                    success=False,
                    error=str(err),
                    duration_ms=round((time.perf_counter() - start) * 1000, 1),
                )
            except Exception as exc:
                err = ToolExecutionError(f"Tool '{name}' raised: {exc}")
                return ToolResult(
                    call_id=call_id,
                    tool=name,
                    success=False,
                    error=str(err),
                    duration_ms=round((time.perf_counter() - start) * 1000, 1),
                )

        return ToolResult(
            call_id=call_id,
            tool=name,
            success=True,
            output=output,
            duration_ms=round((time.perf_counter() - start) * 1000, 1),
        )
