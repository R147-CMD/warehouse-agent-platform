from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.api.domain.agent_protocols import AgentResult
from src.api.domain.identity import IdentityContext
from src.api.services.memory_v2.loader import MemoryLoader
from src.api.services.memory_v2.store import InMemoryMemoryStore
from src.api.services.memory_v2.writer import MemoryWriter
from src.api.services.runtime_v2 import WarehouseAgentPlatformV2


def identity() -> IdentityContext:
    return IdentityContext(
        tenant_id="tenant-1",
        user_id="user-1",
        scopes=("inventory.read",),
        warehouse_scope=("WH-01",),
        authenticated_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_graph_writes_after_answer_then_loads_memory_for_the_next_run() -> None:
    store = InMemoryMemoryStore()
    tasks = []

    async def query_fact(task):
        tasks.append(task)
        return AgentResult(
            task_id=task.task_id,
            status="succeeded",
            summary="查询完成。",
            data={"status": "ok"},
            confidence=0.9,
        )

    platform = WarehouseAgentPlatformV2(
        capability_handlers={"warehouse.fact.query": query_fact},
        memory_loader=MemoryLoader(store),
        memory_writer=MemoryWriter(store),
    )
    first = await platform.process(
        "查询库存状态",
        identity(),
        conversation_id="conversation-1",
        context={
            "memory_candidates": [
                {
                    "memory_key": "report.language",
                    "memory_type": "preference",
                    "content": "KPI 报表默认使用中文",
                    "source": "user",
                    "user_confirmed": True,
                }
            ]
        },
    )
    second = await platform.process(
        "KPI 怎么展示",
        identity(),
        conversation_id="conversation-1",
    )

    assert first["final_answer"]["status"] == "succeeded"
    assert first["memory_write_report"].stored_count == 1
    assert second["memory_context"].long_term_items[0].memory_key == "report.language"
    assert len(second["memory_context"].recent_turns) == 2
    assert tasks[1].context["memory"]["long_term"][0]["content"] == (
        "KPI 报表默认使用中文"
    )
    assert [event["type"] for event in second["events"]][-2:] == [
        "memory.write.completed",
        "run.completed",
    ]


@pytest.mark.asyncio
async def test_memory_writer_failure_does_not_replace_the_business_answer() -> None:
    class FailingWriter:
        async def extract_and_store(self, _run_result, _identity):
            raise ConnectionError("memory database unavailable")

    async def query_fact(task):
        return AgentResult(
            task_id=task.task_id,
            status="succeeded",
            summary="库存状态正常。",
            data={"status": "available"},
            confidence=0.9,
        )

    platform = WarehouseAgentPlatformV2(
        capability_handlers={"warehouse.fact.query": query_fact},
        memory_writer=FailingWriter(),
    )
    result = await platform.process(
        "查询库存状态", identity(), conversation_id="conversation-2"
    )

    assert result["final_answer"]["status"] == "succeeded"
    assert result["final_answer"]["message"] == "库存状态正常。"
    assert result["status"] == "completed"
    assert result["memory_write_report"].status == "failed"
    assert result["memory_write_report"].error_code == "MEMORY_WRITE_UNAVAILABLE"
