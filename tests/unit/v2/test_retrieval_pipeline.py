from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.api.domain.identity import IdentityContext
from src.retrieval.v2.context_builder import ContextBuilder
from src.retrieval.v2.contracts import QueryEnvelope, RetrievalCandidate
from src.retrieval.v2.dense import DenseDocument, InMemoryDenseRetriever
from src.retrieval.v2.fusion import reciprocal_rank_fusion
from src.retrieval.v2.lexical import BM25Document, InMemoryBM25Retriever
from src.retrieval.v2.pipeline import RetrievalPipeline
from src.retrieval.v2.reranker import CrossEncoderReranker


def identity() -> IdentityContext:
    return IdentityContext(
        tenant_id="tenant-a",
        user_id="u-1",
        scopes=("document.read",),
        warehouse_scope=("WH-01",),
        authenticated_at=datetime.now(UTC),
    )


def candidate(
    candidate_id: str, *, rank: int, channel: str, text: str
) -> RetrievalCandidate:
    return RetrievalCandidate(
        candidate_id=candidate_id,
        content=text,
        source_type="document_chunk",
        source_locator={"document_id": "doc-1", "chunk_id": candidate_id},
        channel=channel,
        rank=rank,
        raw_score=999.0 if rank > 1 else 0.01,
        tenant_id="tenant-a",
        warehouse_ids=("WH-01",),
        token_count=4,
    )


def test_rrf_uses_rank_and_merges_duplicate_candidates() -> None:
    lexical = [
        candidate("a", rank=1, channel="lexical", text="alpha"),
        candidate("b", rank=2, channel="lexical", text="beta"),
    ]
    dense = [
        candidate("b", rank=1, channel="dense", text="beta"),
        candidate("a", rank=2, channel="dense", text="alpha"),
    ]

    fused = reciprocal_rank_fusion((lexical, dense), k=60)

    assert [item.candidate.candidate_id for item in fused] == ["a", "b"]
    assert fused[0].fused_score == fused[1].fused_score
    assert fused[0].channels == ("dense", "lexical")


@pytest.mark.asyncio
async def test_pipeline_applies_acl_before_backends_and_uses_both_channels() -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    async def lexical(query: str, *, filters: dict[str, object], limit: int):
        calls.append(("lexical", filters))
        return [candidate("a", rank=1, channel="lexical", text="forklift SOP")]

    async def dense(query: str, *, filters: dict[str, object], limit: int):
        calls.append(("dense", filters))
        return [candidate("b", rank=1, channel="dense", text="equipment procedure")]

    pipeline = RetrievalPipeline(
        lexical_search=lexical,
        dense_search=dense,
        reranker=CrossEncoderReranker(),
        context_builder=ContextBuilder(max_tokens=20),
    )
    query = QueryEnvelope(
        original_query="叉车故障 SOP",
        normalized_query="叉车故障 sop",
        query_type="document_knowledge",
        semantic_queries=("forklift failure procedure",),
    )

    result = await pipeline.retrieve(query, identity())

    assert {name for name, _ in calls} == {"lexical", "dense"}
    assert all(call_filters["tenant_id"] == "tenant-a" for _, call_filters in calls)
    assert all(call_filters["warehouse_ids"] == ("WH-01",) for _, call_filters in calls)
    assert {item.candidate_id for item in result.context.items} == {"a", "b"}
    assert result.degraded_channels == ()


@pytest.mark.asyncio
async def test_dense_failure_is_explicit_and_lexical_result_survives() -> None:
    async def lexical(query: str, *, filters: dict[str, object], limit: int):
        return [candidate("a", rank=1, channel="lexical", text="safe result")]

    async def dense(query: str, *, filters: dict[str, object], limit: int):
        raise TimeoutError("milvus timed out")

    pipeline = RetrievalPipeline(
        lexical_search=lexical,
        dense_search=dense,
        context_builder=ContextBuilder(max_tokens=20),
    )
    query = QueryEnvelope(
        original_query="查 SOP",
        normalized_query="查 sop",
        query_type="document_knowledge",
    )

    result = await pipeline.retrieve(query, identity())

    assert [item.candidate_id for item in result.context.items] == ["a"]
    assert result.degraded_channels == ("dense",)
    assert result.status == "partial"


def test_context_builder_deduplicates_and_respects_token_budget() -> None:
    items = [
        candidate("a", rank=1, channel="lexical", text="same content"),
        candidate("a-copy", rank=2, channel="dense", text="same content"),
        candidate("b", rank=3, channel="dense", text="different content"),
    ]

    context = ContextBuilder(max_tokens=6).build(items)

    assert [item.candidate_id for item in context.items] == ["a"]
    assert context.used_tokens == 4
    assert context.truncated is True


@pytest.mark.asyncio
async def test_bm25_exact_identifier_and_acl_filtering() -> None:
    retriever = InMemoryBM25Retriever(
        (
            BM25Document(
                document_id="d1",
                content="叉车 EQ-001 故障处理流程",
                tenant_id="tenant-a",
                warehouse_ids=("WH-01",),
            ),
            BM25Document(
                document_id="d2",
                content="叉车 EQ-001 机密维修记录",
                tenant_id="tenant-b",
                warehouse_ids=("WH-99",),
            ),
        )
    )

    results = await retriever.retrieve(
        "EQ-001 故障",
        filters={"tenant_id": "tenant-a", "warehouse_ids": ("WH-01",)},
        limit=10,
    )

    assert [item.candidate_id for item in results] == ["d1"]


@pytest.mark.asyncio
async def test_dense_backend_uses_embedding_similarity_and_acl() -> None:
    async def embed(query: str):
        return (1.0, 0.0)

    retriever = InMemoryDenseRetriever(
        (
            DenseDocument("d1", "matching", (0.9, 0.1), "tenant-a", ("WH-01",)),
            DenseDocument("d2", "other tenant", (1.0, 0.0), "tenant-b", ("WH-99",)),
            DenseDocument("d3", "weak", (0.1, 0.9), "tenant-a", ("WH-01",)),
        ),
        embed,
    )

    results = await retriever.retrieve(
        "semantic query",
        filters={"tenant_id": "tenant-a", "warehouse_ids": ("WH-01",)},
        limit=2,
    )

    assert [item.candidate_id for item in results] == ["d1", "d3"]
