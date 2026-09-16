"""Dense retrieval adapter contract."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
import math
from typing import Any

from .contracts import RetrievalCandidate

DenseSearch = Callable[..., Awaitable[list[RetrievalCandidate]]]


class DenseRetriever:
    def __init__(self, search: DenseSearch) -> None:
        self._search = search

    async def retrieve(
        self, query: str, *, filters: dict[str, object], limit: int
    ) -> list[RetrievalCandidate]:
        return await self._search(query, filters=filters, limit=limit)


@dataclass(frozen=True)
class DenseDocument:
    document_id: str
    content: str
    embedding: tuple[float, ...]
    tenant_id: str
    warehouse_ids: tuple[str, ...] = ()
    source_locator: dict[str, Any] = field(default_factory=dict)
    required_scopes: tuple[str, ...] = ()
    parent_id: str | None = None
    neighbor_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        raise ValueError("embedding dimensions do not match")
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


class InMemoryDenseRetriever:
    """Functional cosine-search backend matching the production Dense contract."""

    def __init__(
        self,
        documents: tuple[DenseDocument, ...],
        embed_query: Callable[[str], Awaitable[tuple[float, ...]]],
    ) -> None:
        self.documents = documents
        self.embed_query = embed_query

    async def retrieve(
        self, query: str, *, filters: dict[str, object], limit: int
    ) -> list[RetrievalCandidate]:
        query_embedding = tuple(await self.embed_query(query))
        tenant_id = str(filters["tenant_id"])
        warehouses = set(filters.get("warehouse_ids", ()))
        eligible = [
            document
            for document in self.documents
            if document.tenant_id == tenant_id
            and (
                not document.warehouse_ids
                or bool(set(document.warehouse_ids) & warehouses)
            )
        ]
        scored = sorted(
            ((_cosine(query_embedding, item.embedding), item) for item in eligible),
            key=lambda item: (-item[0], item[1].document_id),
        )
        return [
            RetrievalCandidate(
                candidate_id=document.document_id,
                content=document.content,
                source_type="document_chunk",
                source_locator=document.source_locator
                or {"chunk_id": document.document_id},
                channel="dense",
                rank=rank,
                raw_score=score,
                tenant_id=document.tenant_id,
                warehouse_ids=document.warehouse_ids,
                required_scopes=document.required_scopes,
                parent_id=document.parent_id,
                neighbor_ids=document.neighbor_ids,
                token_count=max(1, len(document.content) // 3),
                metadata=document.metadata,
            )
            for rank, (score, document) in enumerate(scored[:limit], start=1)
        ]
