from datetime import UTC, datetime

import pytest


def _identity():
    from src.api.domain.identity import IdentityContext

    return IdentityContext(
        tenant_id="tenant-a",
        user_id="user-1",
        username="operator",
        roles=("operator",),
        scopes=("inventory.read",),
        warehouse_scope=("WH-01",),
        authenticated_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_v2_graph_runs_isolated_skeleton_to_completion():
    from src.api.graphs.warehouse_graph_v2 import build_warehouse_graph_v2
    from src.api.services.runs.context_v2 import RunIdentityFactory

    identity = _identity()
    run = RunIdentityFactory.create("conversation-1", identity)
    graph = build_warehouse_graph_v2()

    result = await graph.ainvoke(
        {
            "run": run,
            "identity": identity,
            "request": {"message": "查询 WH-01 的库存"},
            "status": "queued",
            "events": [],
        },
        config={"configurable": {"thread_id": run.thread_id}},
    )

    assert result["status"] == "completed"
    assert result["stage"] == "finalized"
    assert result["planning_mode"] == "fast_path"
    assert result["query"].query_type == "structured_fact"
    assert result["plan"].nodes[0].capability == "warehouse.fact.query"
    assert result["compiled_plan"].topological_order == ("query", "answer")
    assert result["ready_node_ids"] == ["query"]
    assert result["final_answer"]["status"] == "partial"
    assert [event["type"] for event in result["events"]] == [
        "run.started",
        "memory.loaded",
        "query.understood",
        "plan.created",
        "plan.compiled",
        "coordination.ready",
        "answer.generated",
        "memory.write.skipped",
        "run.completed",
    ]


@pytest.mark.asyncio
async def test_v2_graph_rejects_blank_message():
    from src.api.graphs.warehouse_graph_v2 import build_warehouse_graph_v2
    from src.api.services.runs.context_v2 import RunIdentityFactory

    identity = _identity()
    run = RunIdentityFactory.create("conversation-1", identity)
    graph = build_warehouse_graph_v2()

    with pytest.raises(ValueError, match="message cannot be blank"):
        await graph.ainvoke(
            {
                "run": run,
                "identity": identity,
                "request": {"message": "  "},
                "status": "queued",
                "events": [],
            },
            config={"configurable": {"thread_id": run.thread_id}},
        )


@pytest.mark.asyncio
async def test_v2_graph_can_execute_compiled_plan_with_registered_agent():
    from src.api.domain.agent_protocols import AgentResult
    from src.api.graphs.warehouse_graph_v2 import (
        WarehouseGraphRuntimeV2,
        build_warehouse_graph_v2,
    )
    from src.api.services.orchestration.agent_executor import (
        AgentExecutorRegistry,
        FunctionAgentExecutor,
    )
    from src.api.services.runs.context_v2 import RunIdentityFactory

    async def query_inventory(task):
        return AgentResult(
            task_id=task.task_id,
            status="succeeded",
            summary="WH-01 当前可用库存 12 件。",
            data={"quantity": 12},
            confidence=0.98,
        )

    executors = AgentExecutorRegistry()
    executors.register("operations-agent-v2", FunctionAgentExecutor(query_inventory))
    identity = _identity()
    run = RunIdentityFactory.create("conversation-2", identity)
    graph = build_warehouse_graph_v2(
        runtime=WarehouseGraphRuntimeV2(executors=executors)
    )

    result = await graph.ainvoke(
        {
            "run": run,
            "identity": identity,
            "request": {"message": "查询 WH-01 的库存"},
            "status": "queued",
            "events": [],
        }
    )

    assert result["final_answer"]["status"] == "succeeded"
    assert "12 件" in result["final_answer"]["message"]
    assert result["node_runs"]["query"].status == "succeeded"
    assert [event["type"] for event in result["events"]].count(
        "coordination.ready"
    ) == 2
