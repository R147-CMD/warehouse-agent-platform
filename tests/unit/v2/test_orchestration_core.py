from datetime import UTC, datetime

import pytest
from pydantic import ValidationError


def _identity(scopes=("inventory.read",)):
    from src.api.domain.identity import IdentityContext

    return IdentityContext(
        tenant_id="tenant-a",
        user_id="user-1",
        username="operator",
        roles=("operator",),
        scopes=scopes,
        warehouse_scope=("WH-01",),
        authenticated_at=datetime.now(UTC),
    )


def _capability(
    capability_id="warehouse.inventory.query",
    owner_id="operations-agent",
    required_scopes=("inventory.read",),
    health_status="available",
    priority=100,
):
    from src.api.services.orchestration.capability_registry import (
        CapabilityDescriptor,
    )

    return CapabilityDescriptor(
        capability_id=capability_id,
        owner_type="agent",
        owner_id=owner_id,
        description="Query warehouse inventory",
        input_schema_ref="AgentTask@1.0",
        output_schema_ref="AgentResult@1.0",
        required_scopes=required_scopes,
        supported_tenants=("tenant-a",),
        risk_level="low",
        read_write_mode="read",
        health_status=health_status,
        priority=priority,
        version="1.0.0",
    )


def test_capability_registry_filters_scope_tenant_and_health():
    from src.api.services.orchestration.capability_registry import CapabilityRegistry

    registry = CapabilityRegistry(
        [
            _capability(owner_id="allowed"),
            _capability(owner_id="offline", health_status="unavailable"),
            _capability(owner_id="write-only", required_scopes=("inventory.write",)),
        ]
    )

    candidates = registry.resolve("warehouse.inventory.query", _identity())

    assert [candidate.owner_id for candidate in candidates] == ["allowed"]


def test_router_uses_highest_priority_eligible_provider():
    from src.api.domain.agent_protocols import AgentTask
    from src.api.services.orchestration.capability_registry import CapabilityRegistry
    from src.api.services.orchestration.router_v2 import RouterV2

    registry = CapabilityRegistry(
        [
            _capability(owner_id="secondary", priority=50),
            _capability(owner_id="primary", priority=100),
        ]
    )
    task = AgentTask(
        task_id="task-1",
        run_id="run-1",
        node_id="query-inventory",
        capability="warehouse.inventory.query",
        objective="query current inventory",
        identity=_identity(),
    )

    decision = RouterV2(registry).route(task)

    assert decision.status == "selected"
    assert decision.owner_id == "primary"


def test_plan_node_requires_bounds_for_map_and_loop():
    from src.api.services.orchestration.models import PlanNode

    with pytest.raises(ValidationError):
        PlanNode(node_id="map-orders", node_type="map")
    with pytest.raises(ValidationError):
        PlanNode(node_id="retry-search", node_type="loop")


def test_plan_compiler_rejects_cycles_and_compiles_valid_dependencies():
    from src.api.services.orchestration.capability_registry import CapabilityRegistry
    from src.api.services.orchestration.compiler import PlanCompileError, PlanCompiler
    from src.api.services.orchestration.models import PlanGraph, PlanNode

    registry = CapabilityRegistry([_capability()])
    compiler = PlanCompiler(registry)
    cyclic = PlanGraph(
        plan_id="plan-cycle",
        version=1,
        objective="invalid",
        nodes=(
            PlanNode(
                node_id="a",
                node_type="task",
                capability="warehouse.inventory.query",
                depends_on=("b",),
            ),
            PlanNode(
                node_id="b",
                node_type="task",
                capability="warehouse.inventory.query",
                depends_on=("a",),
            ),
        ),
    )
    with pytest.raises(PlanCompileError, match="cycle"):
        compiler.compile(cyclic, _identity())

    valid = PlanGraph(
        plan_id="plan-ok",
        version=1,
        objective="query and answer",
        nodes=(
            PlanNode(
                node_id="query",
                node_type="task",
                capability="warehouse.inventory.query",
            ),
            PlanNode(node_id="answer", node_type="answer", depends_on=("query",)),
        ),
    )
    compiled = compiler.compile(valid, _identity())

    assert compiled.topological_order == ("query", "answer")
    assert compiled.bindings["query"].owner_id == "operations-agent"
    assert len(compiled.plan_hash) == 64


def test_coordinator_only_marks_satisfied_dependencies_ready():
    from src.api.services.orchestration.coordinator import Coordinator
    from src.api.services.orchestration.models import NodeRun, PlanGraph, PlanNode

    plan = PlanGraph(
        plan_id="plan-1",
        version=1,
        objective="query and answer",
        nodes=(
            PlanNode(
                node_id="query",
                node_type="task",
                capability="warehouse.inventory.query",
            ),
            PlanNode(node_id="answer", node_type="answer", depends_on=("query",)),
        ),
    )

    first = Coordinator.ready_nodes(plan, {})
    second = Coordinator.ready_nodes(
        plan,
        {"query": NodeRun(node_id="query", status="succeeded", attempt=1)},
    )

    assert [node.node_id for node in first] == ["query"]
    assert [node.node_id for node in second] == ["answer"]


def test_complexity_classifier_uses_fast_path_hybrid_and_clarification():
    from src.api.domain.agent_protocols import MissingInput
    from src.api.services.orchestration.complexity import ComplexityClassifier
    from src.retrieval.v2.contracts import QueryEnvelope

    fast = QueryEnvelope(
        original_query="库存",
        normalized_query="库存",
        query_type="structured_fact",
    )
    hybrid = QueryEnvelope(
        original_query="库存与SOP",
        normalized_query="库存与SOP",
        query_type="hybrid",
    )
    unclear = fast.model_copy(
        update={
            "missing_inputs": (
                MissingInput(field_name="warehouse_id", reason="required"),
            )
        }
    )

    assert ComplexityClassifier.classify(fast).mode == "fast_path"
    assert ComplexityClassifier.classify(hybrid).mode == "llm"
    assert ComplexityClassifier.classify(unclear).mode == "clarify"


def test_repair_budget_is_consumed_without_mutating_previous_value():
    from src.api.services.orchestration.repair import RepairBudget

    budget = RepairBudget(
        reflection_remaining=1, retrieval_rewrite_remaining=2, replan_remaining=2
    )
    updated = budget.consume("reflection")

    assert budget.reflection_remaining == 1
    assert updated.reflection_remaining == 0
    with pytest.raises(ValueError, match="exhausted"):
        updated.consume("reflection")
