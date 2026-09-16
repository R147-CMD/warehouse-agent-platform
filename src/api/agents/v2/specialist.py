"""Small specialist Agent boundary: reason, call services, return protocol data."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from src.api.domain.agent_protocols import AgentResult, AgentTask, ProposedAction
from src.api.domain.errors import AgentError, ErrorCategory


class SpecialistAgent:
    def __init__(
        self,
        agent_id: str,
        capabilities: tuple[str, ...],
        handlers: dict[str, Callable[[AgentTask], Any]],
    ) -> None:
        self.agent_id = agent_id
        self.capabilities = capabilities
        self.handlers = handlers

    async def execute(self, task: AgentTask) -> AgentResult:
        if task.capability not in self.capabilities:
            return self._failure(task, "CAPABILITY_NOT_SUPPORTED", "contract_error")
        handler = self.handlers.get(task.capability)
        if handler is None:
            return self._failure(
                task, "DOMAIN_SERVICE_UNAVAILABLE", "dependency_unavailable"
            )
        try:
            value = handler(task)
            if inspect.isawaitable(value):
                value = await value
            if isinstance(value, AgentResult):
                return value
            if isinstance(value, ProposedAction):
                return AgentResult(
                    task_id=task.task_id,
                    status="succeeded",
                    summary="Action proposal created; no external change has been executed.",
                    proposed_actions=(value,),
                    confidence=1.0,
                )
            if not isinstance(value, dict):
                value = {"result": value}
            return AgentResult(
                task_id=task.task_id,
                status="succeeded",
                summary=str(
                    value.get("summary") or f"{self.agent_id} completed the task."
                ),
                data=value,
                confidence=float(value.get("confidence", 0.8)),
            )
        except Exception as exc:
            return AgentResult(
                task_id=task.task_id,
                status="failed",
                summary=f"{self.agent_id} failed to complete the task.",
                confidence=0.0,
                error=AgentError(
                    code="DOMAIN_HANDLER_FAILED",
                    category=ErrorCategory.INTERNAL,
                    message=f"{type(exc).__name__}: {exc}",
                    retryable=False,
                ),
            )

    @staticmethod
    def _failure(task: AgentTask, code: str, category: str) -> AgentResult:
        return AgentResult(
            task_id=task.task_id,
            status="failed",
            summary=code.replace("_", " ").title(),
            confidence=0.0,
            error=AgentError(
                code=code,
                category=ErrorCategory(category),
                message=code.replace("_", " ").lower(),
                retryable=category == "dependency_unavailable",
            ),
        )
