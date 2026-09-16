"""Executable PlanGraph and node runtime models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.api.domain.agent_protocols import Constraint

NodeType = Literal[
    "task",
    "condition",
    "map",
    "join",
    "reduce",
    "loop",
    "approval",
    "command",
    "verify",
    "answer",
]
NodeStatus = Literal[
    "pending",
    "ready",
    "running",
    "succeeded",
    "partial",
    "blocked",
    "failed",
    "cancelled",
    "skipped",
]


class Predicate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field_path: str = Field(min_length=1, max_length=500)
    operator: Literal["eq", "ne", "in", "not_in", "lt", "lte", "gt", "gte", "exists"]
    value: Any | None = None


class ValueBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source: Literal["constant", "request", "node_output"]
    path: str | None = Field(default=None, max_length=500)
    value: Any | None = None

    @model_validator(mode="after")
    def validate_source_fields(self) -> "ValueBinding":
        if self.source in {"request", "node_output"} and not self.path:
            raise ValueError("request and node_output bindings require a path")
        return self


class RetryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_attempts: int = Field(default=1, ge=1, le=5)
    initial_backoff_seconds: float = Field(default=0.5, ge=0.0, le=60.0)
    max_backoff_seconds: float = Field(default=8.0, ge=0.0, le=300.0)


class ExecutionBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_runtime_seconds: int = Field(default=300, ge=1, le=3600)
    max_model_calls: int = Field(default=8, ge=0, le=100)
    max_tool_calls: int = Field(default=20, ge=0, le=1000)
    max_map_items: int = Field(default=100, ge=1, le=10000)
    max_parallel_nodes: int = Field(default=5, ge=1, le=100)


class PlanNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(min_length=1, max_length=128)
    node_type: NodeType
    capability: str | None = Field(default=None, max_length=200)
    inputs: dict[str, ValueBinding] = Field(default_factory=dict)
    depends_on: tuple[str, ...] = ()
    success_condition: Predicate | None = None
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    timeout_seconds: int = Field(default=60, ge=1, le=900)
    resource_keys: tuple[str, ...] = ()
    on_failure: Literal["stop", "skip", "fallback", "repair"] = "stop"
    max_items: int | None = Field(default=None, ge=1, le=10000)
    max_iterations: int | None = Field(default=None, ge=1, le=10)
    join_policy: Literal["all_success", "min_success_count", "best_effort"] | None = (
        None
    )
    minimum_success_count: int | None = Field(default=None, ge=1)

    @field_validator("depends_on", "resource_keys")
    @classmethod
    def unique_values(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(dict.fromkeys(values))

    @model_validator(mode="after")
    def validate_node_semantics(self) -> "PlanNode":
        if self.node_type == "task" and not self.capability:
            raise ValueError("task nodes require a capability")
        if self.node_type == "map" and self.max_items is None:
            raise ValueError("map nodes require max_items")
        if self.node_type == "loop" and self.max_iterations is None:
            raise ValueError("loop nodes require max_iterations")
        if self.node_type == "join" and self.join_policy is None:
            raise ValueError("join nodes require a join_policy")
        if (
            self.join_policy == "min_success_count"
            and self.minimum_success_count is None
        ):
            raise ValueError("min_success_count joins require minimum_success_count")
        if self.node_id in self.depends_on:
            raise ValueError("a node cannot depend on itself")
        return self


class PlanGraph(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_id: str = Field(min_length=1, max_length=128)
    version: int = Field(ge=1)
    objective: str = Field(min_length=1, max_length=4000)
    assumptions: tuple[str, ...] = ()
    constraints: tuple[Constraint, ...] = ()
    success_criteria: tuple[Predicate, ...] = ()
    nodes: tuple[PlanNode, ...] = Field(min_length=1)
    budgets: ExecutionBudget = Field(default_factory=ExecutionBudget)
    parent_plan_id: str | None = Field(default=None, max_length=128)
    parent_version: int | None = Field(default=None, ge=1)


class NodeRun(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(min_length=1, max_length=128)
    status: NodeStatus = "pending"
    attempt: int = Field(default=0, ge=0)
    owner_id: str | None = Field(default=None, max_length=200)
    output_ref: str | None = Field(default=None, max_length=1000)
    error_code: str | None = Field(default=None, max_length=100)
    started_at: datetime | None = None
    completed_at: datetime | None = None
