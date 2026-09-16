"""Versioned contracts used to exchange work between orchestrator and agents."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .errors import AgentError
from .evidence_protocols import EvidenceRef, EvidenceRequirement
from .identity import IdentityContext

AgentStatus = Literal["succeeded", "partial", "blocked", "failed"]
RiskLevel = Literal["low", "medium", "high", "critical"]


class Constraint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=100)
    operator: Literal["eq", "ne", "in", "not_in", "lt", "lte", "gt", "gte"]
    value: Any
    hard: bool = True


class MissingInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field_name: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=500)
    required_for_execution: bool = True


class ResultRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str = Field(min_length=1, max_length=128)
    status: AgentStatus
    result_uri: str | None = Field(default=None, max_length=1000)


class ResourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    resource_type: str = Field(min_length=1, max_length=100)
    resource_id: str = Field(min_length=1, max_length=256)
    warehouse_id: str | None = Field(default=None, max_length=128)
    expected_version: str | None = Field(default=None, max_length=128)


class ProposedAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action_id: str = Field(min_length=1, max_length=128)
    capability: str = Field(min_length=1, max_length=200)
    target: ResourceRef
    arguments: dict[str, Any]
    expected_effect: str = Field(min_length=1, max_length=1000)
    risk_level: RiskLevel
    required_scopes: tuple[str, ...] = ()
    preconditions: tuple[Constraint, ...] = ()
    idempotency_key: str = Field(min_length=1, max_length=256)
    evidence_refs: tuple[EvidenceRef, ...] = ()

    @field_validator("idempotency_key", "capability", "expected_effect")
    @classmethod
    def reject_blank_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("required action text cannot be blank")
        return normalized


class AgentMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    duration_ms: int | None = Field(default=None, ge=0)
    model_calls: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)


class AgentTask(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    node_id: str = Field(min_length=1, max_length=128)
    capability: str = Field(min_length=1, max_length=200)
    objective: str = Field(min_length=1, max_length=4000)
    inputs: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    constraints: tuple[Constraint, ...] = ()
    identity: IdentityContext
    dependency_results: tuple[ResultRef, ...] = ()
    evidence_requirements: tuple[EvidenceRequirement, ...] = ()
    deadline_at: datetime | None = None
    schema_version: str = "1.0"

    @field_validator("task_id", "run_id", "node_id", "capability", "objective")
    @classmethod
    def reject_blank_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("required task text cannot be blank")
        return normalized


class AgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str = Field(min_length=1, max_length=128)
    status: AgentStatus
    summary: str = Field(min_length=1, max_length=4000)
    data: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: tuple[EvidenceRef, ...] = ()
    proposed_actions: tuple[ProposedAction, ...] = ()
    confidence: float = Field(ge=0.0, le=1.0)
    missing_inputs: tuple[MissingInput, ...] = ()
    warnings: tuple[str, ...] = ()
    error: AgentError | None = None
    metrics: AgentMetrics = Field(default_factory=AgentMetrics)
    schema_version: str = "1.0"

    @model_validator(mode="after")
    def validate_status_error_contract(self) -> "AgentResult":
        if self.status == "failed" and self.error is None:
            raise ValueError("failed agent results require a structured error")
        if self.status == "succeeded" and self.error is not None:
            raise ValueError("succeeded agent results cannot include an error")
        return self
