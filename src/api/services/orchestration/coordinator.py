"""Deterministic READY-set calculation for compiled plan execution."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

from src.api.domain.agent_protocols import AgentResult, AgentTask, ResultRef
from src.api.domain.errors import AgentError, ErrorCategory
from src.api.domain.identity import IdentityContext
from src.api.services.runs.context_v2 import RunExecutionContextV2

from .agent_executor import AgentExecutorRegistry
from .compiler import CompiledPlan
from .models import NodeRun, PlanGraph, PlanNode


class CoordinationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    node_runs: dict[str, NodeRun]
    results: tuple[AgentResult, ...]


class Coordinator:
    TERMINAL_NODE_STATUSES = frozenset(
        {"succeeded", "partial", "blocked", "failed", "cancelled", "skipped"}
    )

    def __init__(
        self,
        executors: AgentExecutorRegistry | None = None,
        *,
        max_parallel_nodes: int = 5,
    ) -> None:
        self.executors = executors or AgentExecutorRegistry()
        self.max_parallel_nodes = max_parallel_nodes

    @staticmethod
    def ready_nodes(
        plan: PlanGraph,
        node_runs: dict[str, NodeRun],
    ) -> list[PlanNode]:
        nodes_by_id = {node.node_id: node for node in plan.nodes}
        ready: list[PlanNode] = []
        for node in plan.nodes:
            existing = node_runs.get(node.node_id)
            if existing and existing.status != "pending":
                continue
            if node.node_type == "join":
                dependencies_satisfied = all(
                    dependency in node_runs
                    and node_runs[dependency].status
                    in Coordinator.TERMINAL_NODE_STATUSES
                    for dependency in node.depends_on
                )
            else:
                dependencies_satisfied = all(
                    dependency in node_runs
                    and node_runs[dependency].status == "succeeded"
                    for dependency in node.depends_on
                )
            if dependencies_satisfied:
                ready.append(nodes_by_id[node.node_id])
        return ready

    @classmethod
    def advance_control_nodes(
        cls,
        plan: PlanGraph,
        node_runs: dict[str, NodeRun],
    ) -> dict[str, NodeRun]:
        """Complete deterministic non-side-effect control nodes to a fixed point."""

        updated = dict(node_runs)
        while True:
            advanced = False
            for node in cls.ready_nodes(plan, updated):
                if node.node_type not in {"join", "reduce", "condition"}:
                    continue
                dependency_runs = [updated[item] for item in node.depends_on]
                if node.node_type == "join":
                    if node.join_policy == "all_success":
                        status = "succeeded"
                    elif node.join_policy == "min_success_count":
                        successes = sum(
                            item.status == "succeeded" for item in dependency_runs
                        )
                        status = (
                            "succeeded"
                            if successes >= (node.minimum_success_count or 1)
                            else "partial"
                        )
                    else:
                        status = (
                            "succeeded"
                            if any(
                                item.status == "succeeded" for item in dependency_runs
                            )
                            else "partial"
                        )
                else:
                    # Reducers and safe predicates are pure graph operations. Their
                    # payload evaluation lives in the node implementation/provider.
                    status = "succeeded"
                updated[node.node_id] = NodeRun(
                    node_id=node.node_id,
                    status=status,
                    attempt=1,
                    started_at=datetime.now(UTC),
                    completed_at=datetime.now(UTC),
                )
                advanced = True
            if not advanced:
                return updated

    async def execute_ready(
        self,
        *,
        compiled: CompiledPlan,
        run: RunExecutionContextV2,
        identity: IdentityContext,
        request: dict[str, object],
        node_runs: dict[str, NodeRun],
        previous_results: tuple[AgentResult, ...],
    ) -> CoordinationUpdate:
        ready = [
            node
            for node in self.ready_nodes(compiled.plan, node_runs)
            if node.node_type == "task"
        ]
        semaphore = asyncio.Semaphore(
            min(self.max_parallel_nodes, compiled.plan.budgets.max_parallel_nodes)
        )
        previous_by_node = {
            result.task_id.rsplit(":", 1)[-1]: result for result in previous_results
        }

        async def execute(node: PlanNode) -> tuple[NodeRun, AgentResult]:
            async with semaphore:
                started = datetime.now(UTC)
                task_id = f"{run.run_id}:{node.node_id}"
                dependency_results = tuple(
                    ResultRef(task_id=result.task_id, status=result.status)
                    for dependency in node.depends_on
                    if (result := previous_by_node.get(dependency)) is not None
                )
                task = AgentTask(
                    task_id=task_id,
                    run_id=run.run_id,
                    node_id=node.node_id,
                    capability=node.capability or "",
                    objective=compiled.plan.objective,
                    inputs=self._resolve_inputs(node, request, previous_by_node),
                    context=self._agent_context(request),
                    constraints=compiled.plan.constraints,
                    identity=identity,
                    dependency_results=dependency_results,
                )
                binding = compiled.bindings[node.node_id]
                executor = self.executors.get(binding.owner_id)
                if executor is None:
                    result = AgentResult(
                        task_id=task_id,
                        status="failed",
                        summary=f"Agent provider {binding.owner_id} is not available.",
                        confidence=0.0,
                        error=AgentError(
                            code="AGENT_PROVIDER_UNAVAILABLE",
                            category=ErrorCategory.DEPENDENCY_UNAVAILABLE,
                            message=f"No executor registered for {binding.owner_id}",
                            retryable=True,
                        ),
                    )
                else:
                    try:
                        result = await asyncio.wait_for(
                            executor.execute(task), timeout=node.timeout_seconds
                        )
                    except TimeoutError:
                        result = AgentResult(
                            task_id=task_id,
                            status="failed",
                            summary="Agent execution timed out.",
                            confidence=0.0,
                            error=AgentError(
                                code="AGENT_TIMEOUT",
                                category=ErrorCategory.TIMEOUT,
                                message=f"Node {node.node_id} timed out",
                                retryable=True,
                            ),
                        )
                completed = datetime.now(UTC)
                return (
                    NodeRun(
                        node_id=node.node_id,
                        status=result.status,
                        attempt=1,
                        owner_id=binding.owner_id,
                        error_code=result.error.code if result.error else None,
                        started_at=started,
                        completed_at=completed,
                    ),
                    result,
                )

        completed = await asyncio.gather(*(execute(node) for node in ready))
        updated_runs = dict(node_runs)
        results = []
        for node_run, result in completed:
            updated_runs[node_run.node_id] = node_run
            results.append(result)
        return CoordinationUpdate(node_runs=updated_runs, results=tuple(results))

    @staticmethod
    def _resolve_inputs(
        node: PlanNode,
        request: dict[str, object],
        previous_by_node: dict[str, AgentResult],
    ) -> dict[str, object]:
        resolved: dict[str, object] = {}
        for name, binding in node.inputs.items():
            if binding.source == "constant":
                resolved[name] = binding.value
            elif binding.source == "request":
                resolved[name] = Coordinator._read_path(request, binding.path or "")
            else:
                path = binding.path or ""
                node_id, _, output_path = path.partition(".")
                result = previous_by_node.get(node_id)
                resolved[name] = (
                    Coordinator._read_path(result.data, output_path)
                    if result is not None
                    else None
                )
        return resolved

    @staticmethod
    def _agent_context(request: dict[str, object]) -> dict[str, object]:
        """Expose only orchestrator-approved context instead of raw client metadata."""

        raw_context = request.get("context")
        if not isinstance(raw_context, dict):
            return {}
        memory = raw_context.get("memory")
        return {"memory": memory} if isinstance(memory, dict) else {}

    @staticmethod
    def _read_path(value: object, path: str) -> object:
        current = value
        for part in filter(None, path.split(".")):
            if isinstance(current, dict):
                current = current.get(part)
            else:
                current = getattr(current, part, None)
        return current
