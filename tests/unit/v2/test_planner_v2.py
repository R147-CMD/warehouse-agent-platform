from datetime import UTC, datetime

import pytest


def _identity():
    from src.api.domain.identity import IdentityContext

    return IdentityContext(
        tenant_id="tenant-a",
        user_id="user-1",
        username="operator",
        roles=("supervisor",),
        scopes=("inventory.read", "operations.propose"),
        warehouse_scope=("WH-01",),
        authenticated_at=datetime.now(UTC),
    )


def test_predicate_evaluator_only_reads_declared_field_path():
    from src.api.services.orchestration.models import Predicate
    from src.api.services.orchestration.predicates import PredicateEvaluator

    context = {"results": {"query": {"count": 3}}}

    assert PredicateEvaluator.evaluate(
        Predicate(field_path="results.query.count", operator="gte", value=2),
        context,
    )
    assert not PredicateEvaluator.evaluate(
        Predicate(field_path="results.query.count", operator="eq", value=0),
        context,
    )


def test_default_htn_registry_expands_rebalance_template():
    from src.api.services.orchestration.htn_registry import build_default_htn_registry

    plan = build_default_htn_registry().expand(
        "rebalance_picking_tasks.v1",
        objective="重平衡今晚拣选任务",
    )

    assert plan.version == 1
    assert [node.node_id for node in plan.nodes] == [
        "query_tasks",
        "query_workforce",
        "build_proposal",
        "approval",
        "command",
        "verify",
        "answer",
    ]


@pytest.mark.asyncio
async def test_planner_builds_fast_path_for_single_fact_query():
    from src.api.services.orchestration.htn_registry import build_default_htn_registry
    from src.api.services.orchestration.planner import PlannerV2
    from src.retrieval.v2.query_understanding import QueryUnderstandingService

    query = QueryUnderstandingService().parse(
        "查询 WH-01 库存",
        _identity(),
        datetime(2026, 9, 7, tzinfo=UTC),
    )
    result = await PlannerV2(build_default_htn_registry()).plan(query)

    assert result.mode == "fast_path"
    assert result.plan is not None
    assert result.plan.nodes[0].capability == "warehouse.fact.query"


@pytest.mark.asyncio
async def test_planner_builds_parallel_hybrid_candidate_without_free_form_tools():
    from src.api.services.orchestration.htn_registry import build_default_htn_registry
    from src.api.services.orchestration.planner import PlannerV2
    from src.retrieval.v2.query_understanding import QueryUnderstandingService

    query = QueryUnderstandingService().parse(
        "查询 EQ-03 当前故障状态，并给出处置 SOP",
        _identity(),
        datetime(2026, 9, 7, tzinfo=UTC),
    )
    result = await PlannerV2(build_default_htn_registry()).plan(query)

    assert result.mode == "llm"
    assert result.plan is not None
    assert result.plan.nodes[0].capability == "warehouse.fact.query"
    assert result.plan.nodes[1].capability == "knowledge.search"
    assert result.plan.nodes[2].node_type == "join"


@pytest.mark.asyncio
async def test_planner_uses_htn_for_rebalance_action():
    from src.api.services.orchestration.htn_registry import build_default_htn_registry
    from src.api.services.orchestration.planner import PlannerV2
    from src.retrieval.v2.query_understanding import QueryUnderstandingService

    query = QueryUnderstandingService().parse(
        "重平衡 WH-01 今晚的拣选任务",
        _identity(),
        datetime(2026, 9, 7, tzinfo=UTC),
    )
    result = await PlannerV2(build_default_htn_registry()).plan(query)

    assert result.mode == "htn"
    assert result.plan is not None
    assert any(node.node_type == "approval" for node in result.plan.nodes)


@pytest.mark.asyncio
async def test_generic_controlled_action_htn_has_resolvable_dependencies():
    from src.api.services.orchestration.htn_registry import build_default_htn_registry
    from src.api.services.orchestration.planner import PlannerV2
    from src.retrieval.v2.query_understanding import QueryUnderstandingService

    query = QueryUnderstandingService().parse(
        "更新 WH-01 的仓库配置",
        _identity(),
        datetime(2026, 9, 7, tzinfo=UTC),
    )
    result = await PlannerV2(build_default_htn_registry()).plan(query)

    assert result.plan is not None
    node_ids = {node.node_id for node in result.plan.nodes}
    assert all(
        dependency in node_ids
        for node in result.plan.nodes
        for dependency in node.depends_on
    )


@pytest.mark.asyncio
async def test_planner_selects_specific_sap_assignment_htn() -> None:
    from src.api.services.orchestration.htn_registry import build_default_htn_registry
    from src.api.services.orchestration.planner import PlannerV2
    from src.retrieval.v2.query_understanding import QueryUnderstandingService

    query = QueryUnderstandingService().parse(
        "将 SAP 仓库订单 2000005003 分配给 RES2",
        _identity(),
        datetime(2026, 9, 7, tzinfo=UTC),
    )
    result = await PlannerV2(build_default_htn_registry()).plan(query)

    assert result.mode == "htn"
    assert result.plan is not None
    assert result.plan.nodes[1].capability == "sap.ewm.order.assign.propose"
