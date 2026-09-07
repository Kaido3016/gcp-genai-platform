"""Calculator tool.

Security note (Phase 7/13): this deliberately does NOT use `eval`/`exec`.
Arithmetic expressions are parsed with `ast` and walked against a strict
allowlist of node types and operators, so the tool cannot be used to run
arbitrary code regardless of how the model or a malicious prompt phrases
the "expression" argument.
"""

from __future__ import annotations

import ast
import operator
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from app.core.exceptions import ToolExecutionError
from app.schemas.agent import CalculatorArgs, ToolName
from app.services.agent.tools.base import Tool

_ALLOWED_BINOPS: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}
_ALLOWED_UNARYOPS: dict[type[ast.unaryop], Callable[[Any], Any]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ToolExecutionError("Only numeric constants are allowed.")
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        return _ALLOWED_BINOPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARYOPS:
        return _ALLOWED_UNARYOPS[type(node.op)](_safe_eval(node.operand))
    raise ToolExecutionError(f"Disallowed expression element: {type(node).__name__}")


def safe_arithmetic_eval(expression: str) -> float:
    try:
        parsed = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ToolExecutionError(f"Invalid expression syntax: {exc}") from exc
    return _safe_eval(parsed)


class CalculatorTool(Tool):
    name = ToolName.CALCULATOR
    description = (
        "Evaluate a basic arithmetic expression (+, -, *, /, %, **, "
        "parentheses). Use this instead of doing math yourself when the "
        "user asks a numeric question."
    )
    allowed_for_all = True

    def run(self, args: BaseModel, *, context: dict[str, Any]) -> Any:
        assert isinstance(args, CalculatorArgs)
        result = safe_arithmetic_eval(args.expression)
        return {"expression": args.expression, "result": result}
