"""Safe predicate evaluation for PlanGraph conditions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import Predicate

_MISSING = object()


class PredicateEvaluator:
    @classmethod
    def evaluate(cls, predicate: Predicate, context: Mapping[str, Any]) -> bool:
        actual = cls._resolve(predicate.field_path, context)
        if predicate.operator == "exists":
            return actual is not _MISSING
        if actual is _MISSING:
            return False

        expected = predicate.value
        operations = {
            "eq": lambda: actual == expected,
            "ne": lambda: actual != expected,
            "in": lambda: actual in expected,
            "not_in": lambda: actual not in expected,
            "lt": lambda: actual < expected,
            "lte": lambda: actual <= expected,
            "gt": lambda: actual > expected,
            "gte": lambda: actual >= expected,
        }
        try:
            return bool(operations[predicate.operator]())
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _resolve(field_path: str, context: Mapping[str, Any]) -> Any:
        if any(part.startswith("_") for part in field_path.split(".")):
            return _MISSING
        current: Any = context
        for part in field_path.split("."):
            if isinstance(current, Mapping):
                current = current.get(part, _MISSING)
            else:
                current = getattr(current, part, _MISSING)
            if current is _MISSING:
                return _MISSING
        return current
