"""Uniform execution boundary for native V2 and legacy specialist agents."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from src.api.domain.agent_protocols import AgentResult, AgentTask


class AgentExecutor(Protocol):
    async def execute(self, task: AgentTask) -> AgentResult: ...


AgentHandler = Callable[[AgentTask], AgentResult | Awaitable[AgentResult]]


class FunctionAgentExecutor:
    def __init__(self, handler: AgentHandler) -> None:
        self._handler = handler

    async def execute(self, task: AgentTask) -> AgentResult:
        result = self._handler(task)
        if inspect.isawaitable(result):
            result = await result
        return AgentResult.model_validate(result)


class LegacyAgentAdapter:
    """Translate AgentTask to a legacy query callable and normalize its response."""

    def __init__(self, process_query: Callable[..., Any]) -> None:
        self._process_query = process_query

    async def execute(self, task: AgentTask) -> AgentResult:
        result = self._process_query(task.objective, task.identity.user_id)
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, AgentResult):
            return result
        payload = result if isinstance(result, dict) else {"result": result}
        summary = str(
            payload.get("natural_language")
            or payload.get("summary")
            or payload.get("response")
            or "Legacy agent completed the task."
        )
        return AgentResult(
            task_id=task.task_id,
            status="succeeded",
            summary=summary,
            data=payload,
            confidence=float(payload.get("confidence", 0.7)),
        )


class AgentExecutorRegistry:
    def __init__(self) -> None:
        self._executors: dict[str, AgentExecutor] = {}

    def register(self, owner_id: str, executor: AgentExecutor) -> None:
        if owner_id in self._executors:
            raise ValueError(f"duplicate agent executor: {owner_id}")
        self._executors[owner_id] = executor

    def get(self, owner_id: str) -> AgentExecutor | None:
        return self._executors.get(owner_id)

    def owners(self) -> tuple[str, ...]:
        return tuple(sorted(self._executors))
