from __future__ import annotations

from datetime import UTC, datetime

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from src.api.domain.identity import IdentityContext
from src.api.domain.agent_protocols import AgentResult
from src.api.services.runtime_v2 import WarehouseAgentPlatformV2
from src.retrieval.v2.context_builder import ContextBuilder
from src.retrieval.v2.dense import DenseDocument, InMemoryDenseRetriever
from src.retrieval.v2.lexical import BM25Document, InMemoryBM25Retriever
from src.retrieval.v2.pipeline import RetrievalPipeline


@pytest.mark.asyncio
async def test_query_to_hybrid_retrieval_evidence_agent_and_answer() -> None:
    lexical = InMemoryBM25Retriever(
        (
            BM25Document(
                "chunk-1",
                "叉车故障时先停车并切断电源",
                "tenant-1",
                ("WH-01",),
                source_locator={"document_id": "sop-1", "page": 2},
            ),
        )
    )

    async def embed(_query: str):
        return (1.0, 0.0)

    dense = InMemoryDenseRetriever(
        (
            DenseDocument(
                "chunk-1",
                "叉车故障时先停车并切断电源",
                (1.0, 0.0),
                "tenant-1",
                ("WH-01",),
                source_locator={"document_id": "sop-1", "page": 2},
            ),
        ),
        embed,
    )

    async def query_fact(task):
        return AgentResult(
            task_id=task.task_id,
            status="succeeded",
            summary="设备故障状态已读取。",
            data={"status": "fault"},
            confidence=0.95,
        )

    platform = WarehouseAgentPlatformV2(
        retrieval=RetrievalPipeline(
            lexical_search=lexical.retrieve,
            dense_search=dense.retrieve,
            context_builder=ContextBuilder(max_tokens=100),
        ),
        capability_handlers={"warehouse.fact.query": query_fact},
    )
    identity = IdentityContext(
        tenant_id="tenant-1",
        user_id="u1",
        scopes=("document.read", "inventory.read"),
        warehouse_scope=("WH-01",),
        authenticated_at=datetime.now(UTC),
    )

    result = await platform.process(
        "叉车故障 SOP 怎么处理", identity, conversation_id="c1", require_evidence=True
    )

    assert result["final_answer"]["status"] == "succeeded"
    assert any(item.evidence_refs for item in result["agent_results"])
    assert result["evidence_refs"][0].source_locator["document_id"] == "sop-1"


@pytest.mark.asyncio
async def test_platform_passes_run_thread_to_langgraph_checkpointer() -> None:
    async def query_fact(task):
        return AgentResult(
            task_id=task.task_id,
            status="succeeded",
            summary="库存状态已读取。",
            data={"status": "available"},
            confidence=0.9,
        )

    checkpointer = InMemorySaver()
    platform = WarehouseAgentPlatformV2(
        capability_handlers={"warehouse.fact.query": query_fact},
        checkpointer=checkpointer,
    )
    identity = IdentityContext(
        tenant_id="tenant-1",
        user_id="u1",
        scopes=("inventory.read",),
        warehouse_scope=("WH-01",),
        authenticated_at=datetime.now(UTC),
    )

    result = await platform.process(
        "查询库存状态", identity, conversation_id="checkpoint-conversation"
    )
    saved = await checkpointer.aget_tuple(
        {"configurable": {"thread_id": result["run"].thread_id}}
    )

    assert saved is not None
    assert saved.checkpoint["channel_values"]["stage"] == "finalized"
