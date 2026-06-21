from __future__ import annotations

import ast
import json
import operator
import re
from pathlib import Path
from typing import Any, Iterator, Optional


_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_UNARY_OPERATORS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_STOP_TIME_PATTERN = re.compile(
    r"\bstop\s*=\s*\{.*?\btime\s*=\s*([0-9eE+\-*/().\s]+)",
    re.DOTALL,
)


def _safe_number(expression: str) -> Optional[float]:
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError:
        return None

    def evaluate(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
            return _BINARY_OPERATORS[type(node.op)](
                evaluate(node.left), evaluate(node.right)
            )
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
            return _UNARY_OPERATORS[type(node.op)](evaluate(node.operand))
        raise ValueError("Unsupported expression")

    try:
        value = evaluate(tree)
    except (ValueError, TypeError, ZeroDivisionError, OverflowError):
        return None
    return value if value >= 0 else None


def _walk(value: Any) -> Iterator[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def parse_planned_test_seconds(path: str | Path) -> Optional[float]:
    source = Path(path)
    try:
        with source.open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None

    for item in _walk(data):
        if not isinstance(item, dict):
            continue
        if str(item.get("templateName", "")).strip() != "stop_time":
            continue
        value = _safe_number(str(item.get("templateValue", "")))
        if value is not None:
            return value

    for item in _walk(data):
        if not isinstance(item, str):
            continue
        match = _STOP_TIME_PATTERN.search(item)
        if match:
            value = _safe_number(match.group(1))
            if value is not None:
                return value
    return None
