from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.api.domain.agent_protocols import AgentResult
from src.api.domain.identity import IdentityContext
from src.api.services.orchestration.agent_executor import (
    AgentExecutorRegistry,
    FunctionAgentExecutor,
)
from src.api.services.orchestration.capability_registry import (
    CapabilityDescriptor,
    CapabilityRegistry,
)
from src.api.services.orchestration.compiler import PlanCompiler
from src.api.services.orchestration.coordinator import Coordinator
from src.api.services.orchestration.models import PlanGraph, PlanNode, ValueBinding
from src.api.services.runs.context_v2 import RunIdentityFactory


def identity() -> IdentityContext:
    return IdentityContext(
        tenant_id="t1",
        user_id="u1",
        scopes=("inventory.read",),
        warehouse_scope=("WH-01",),
        authenticated_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_coordinator_packages_task_and_dispatches_registered_agent() -> None:
    seen = []

    async def handler(task):
        seen.append(task)
        return AgentResult(
            task_id=task.task_id,
            status="succeeded",
            summary="库存为 12",
            data={"quantity": 12},
            confidence=0.99,
        )

    descriptors = CapabilityRegistry(
        [
            CapabilityDescriptor(
                capability_id="warehouse.fact.query",
                owner_type="agent",
                owner_id="operations-agent-v2",
                description="facts",
                input_schema_ref="AgentTask@1.0",
                output_schema_ref="AgentResult@1.0",
                required_scopes=("inventory.read",),
                version="1.0.0",
            )
        ]
    )
    executors = AgentExecutorRegistry()
    executors.register("operations-agent-v2", FunctionAgentExecutor(handler))
    plan = PlanGraph(
        plan_id="p1",
        version=1,
        objective="query stock",
        nodes=(
            PlanNode(
                node_id="query",
                node_type="task",
                capability="warehouse.fact.query",
                inputs={"query": ValueBinding(source="request", path="message")},
            ),
            PlanNode(node_id="answer", node_type="answer", depends_on=("query",)),
        ),
    )
    compiled = PlanCompiler(descriptors).compile(plan, identity())
    run = RunIdentityFactory.create(
        conversation_id="c1", request_id="r1", identity=identity()
    )

    update = await Coordinator(executors).execute_ready(
        compiled=compiled,
        run=run,
        identity=identity(),
        request={"message": "SKU-1 库存"},
        node_runs={},
        previous_results=(),
    )

    assert update.node_runs["query"].status == "succeeded"
    assert update.results[0].data == {"quantity": 12}
    assert seen[0].objective == "query stock"
    assert seen[0].inputs["query"] == "SKU-1 库存"


@pytest.mark.asyncio
async def test_missing_executor_is_failed_not_fake_success() -> None:
    registry = CapabilityRegistry(
        [
            CapabilityDescriptor(
                capability_id="equipment.query",
                owner_type="agent",
                owner_id="equipment-agent-v2",
                description="equipment",
                input_schema_ref="AgentTask@1.0",
                output_schema_ref="AgentResult@1.0",
                version="1.0.0",
            )
        ]
    )
    plan = PlanGraph(
        plan_id="p2",
        version=1,
        objective="equipment",
        nodes=(PlanNode(node_id="q", node_type="task", capability="equipment.query"),),
    )
    compiled = PlanCompiler(registry).compile(plan, identity())
    run = RunIdentityFactory.create(
        conversation_id="c", request_id="r", identity=identity()
    )

    update = await Coordinator(AgentExecutorRegistry()).execute_ready(
        compiled=compiled,
        run=run,
        identity=identity(),
        request={},
        node_runs={},
        previous_results=(),
    )

    assert update.results[0].status == "failed"
    assert update.results[0].error.category == "dependency_unavailable"
