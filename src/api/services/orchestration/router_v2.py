"""Constraint-first routing for already planned AgentTask objects."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.api.domain.agent_protocols import AgentTask

from .capability_registry import CapabilityRegistry


class RouteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["selected", "unavailable", "ambiguous"]
    capability_id: str
    owner_type: Literal["agent", "service", "tool"] | None = None
    owner_id: str | None = None
    owner_version: str | None = None
    reason_codes: tuple[str, ...] = ()
    candidate_owner_ids: tuple[str, ...] = ()
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class RouterV2:
    def __init__(self, registry: CapabilityRegistry) -> None:
        self._registry = registry

    def route(self, task: AgentTask) -> RouteDecision:
        candidates = self._registry.resolve(task.capability, task.identity)
        if not candidates:
            return RouteDecision(
                status="unavailable",
                capability_id=task.capability,
                reason_codes=("no_eligible_provider",),
            )

        selected = candidates[0]
        return RouteDecision(
            status="selected",
            capability_id=task.capability,
            owner_type=selected.owner_type,
            owner_id=selected.owner_id,
            owner_version=selected.version,
            reason_codes=("hard_constraints_passed", "highest_priority"),
            candidate_owner_ids=tuple(item.owner_id for item in candidates),
            confidence=1.0 if len(candidates) == 1 else 0.9,
        )
