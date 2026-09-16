"""Static verification and deterministic compilation of candidate plans."""

from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
import json

from pydantic import BaseModel, ConfigDict, Field

from src.api.domain.identity import IdentityContext

from .capability_registry import CapabilityDescriptor, CapabilityRegistry
from .models import PlanGraph


class PlanCompileError(ValueError):
    pass


class CompileReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    normalized: bool = True
    node_count: int = Field(ge=1)
    bound_capability_count: int = Field(ge=0)
    warnings: tuple[str, ...] = ()


class CompiledPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    plan: PlanGraph
    topological_order: tuple[str, ...]
    bindings: dict[str, CapabilityDescriptor]
    plan_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    report: CompileReport


class PlanCompiler:
    def __init__(self, registry: CapabilityRegistry) -> None:
        self._registry = registry

    def compile(
        self,
        plan: PlanGraph,
        identity: IdentityContext,
    ) -> CompiledPlan:
        nodes = {node.node_id: node for node in plan.nodes}
        if len(nodes) != len(plan.nodes):
            raise PlanCompileError("duplicate node IDs are not allowed")

        for node in plan.nodes:
            missing = [
                dependency for dependency in node.depends_on if dependency not in nodes
            ]
            if missing:
                raise PlanCompileError(
                    f"node {node.node_id} has missing dependencies: {missing}"
                )

        topological_order = self._topological_order(plan)
        bindings: dict[str, CapabilityDescriptor] = {}
        for node in plan.nodes:
            if node.node_type != "task":
                continue
            candidates = self._registry.resolve(node.capability or "", identity)
            if not candidates:
                raise PlanCompileError(
                    f"node {node.node_id} has no eligible capability provider"
                )
            bindings[node.node_id] = candidates[0]

        serialized = json.dumps(
            plan.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return CompiledPlan(
            plan=plan,
            topological_order=topological_order,
            bindings=bindings,
            plan_hash=sha256(serialized.encode("utf-8")).hexdigest(),
            report=CompileReport(
                node_count=len(plan.nodes),
                bound_capability_count=len(bindings),
            ),
        )

    @staticmethod
    def _topological_order(plan: PlanGraph) -> tuple[str, ...]:
        indegree = {node.node_id: len(node.depends_on) for node in plan.nodes}
        dependents: dict[str, list[str]] = defaultdict(list)
        order_index = {node.node_id: index for index, node in enumerate(plan.nodes)}
        for node in plan.nodes:
            for dependency in node.depends_on:
                dependents[dependency].append(node.node_id)

        ready = sorted(
            (node_id for node_id, degree in indegree.items() if degree == 0),
            key=order_index.__getitem__,
        )
        ordered: list[str] = []
        while ready:
            node_id = ready.pop(0)
            ordered.append(node_id)
            for dependent in sorted(dependents[node_id], key=order_index.__getitem__):
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    ready.append(dependent)
                    ready.sort(key=order_index.__getitem__)

        if len(ordered) != len(plan.nodes):
            raise PlanCompileError("plan contains a dependency cycle")
        return tuple(ordered)
