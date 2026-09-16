"""Lexical retrieval adapter contract."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from collections import Counter
from dataclasses import dataclass, field
import math
import re
from typing import Any

from .contracts import RetrievalCandidate

LexicalSearch = Callable[..., Awaitable[list[RetrievalCandidate]]]


class LexicalRetriever:
    def __init__(self, search: LexicalSearch) -> None:
        self._search = search

    async def retrieve(
        self, query: str, *, filters: dict[str, object], limit: int
    ) -> list[RetrievalCandidate]:
        return await self._search(query, filters=filters, limit=limit)


@dataclass(frozen=True)
class BM25Document:
    document_id: str
    content: str
    tenant_id: str
    warehouse_ids: tuple[str, ...] = ()
    source_locator: dict[str, Any] = field(default_factory=dict)
    required_scopes: tuple[str, ...] = ()
    parent_id: str | None = None
    neighbor_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


def _lexical_terms(text: str) -> list[str]:
    lowered = text.lower()
    words = re.findall(r"[a-z0-9][a-z0-9_.:/-]*", lowered)
    chinese_runs = re.findall(r"[\u4e00-\u9fff]+", lowered)
    chars = [char for run in chinese_runs for char in run]
    bigrams = [
        run[index : index + 2] for run in chinese_runs for index in range(len(run) - 1)
    ]
    return [*words, *chars, *bigrams]


class InMemoryBM25Retriever:
    """Functional BM25 reference backend for local/dev and deterministic tests."""

    def __init__(
        self,
        documents: tuple[BM25Document, ...] = (),
        *,
        k1: float = 1.2,
        b: float = 0.75,
    ) -> None:
        self.documents = documents
        self.k1 = k1
        self.b = b

    async def retrieve(
        self, query: str, *, filters: dict[str, object], limit: int
    ) -> list[RetrievalCandidate]:
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
        if not eligible:
            return []
        tokenized = [_lexical_terms(document.content) for document in eligible]
        average_length = sum(map(len, tokenized)) / max(1, len(tokenized))
        query_terms = set(_lexical_terms(query))
        document_frequency = Counter(
            term for terms in tokenized for term in set(terms) if term in query_terms
        )
        scored = []
        for document, terms in zip(eligible, tokenized, strict=True):
            frequencies = Counter(terms)
            score = 0.0
            for term in query_terms:
                frequency = frequencies[term]
                if not frequency:
                    continue
                frequency_docs = document_frequency[term]
                inverse_frequency = math.log(
                    1 + (len(eligible) - frequency_docs + 0.5) / (frequency_docs + 0.5)
                )
                denominator = frequency + self.k1 * (
                    1 - self.b + self.b * len(terms) / max(average_length, 1)
                )
                score += inverse_frequency * frequency * (self.k1 + 1) / denominator
            if score > 0:
                scored.append((score, document))
        scored.sort(key=lambda item: (-item[0], item[1].document_id))
        return [
            RetrievalCandidate(
                candidate_id=document.document_id,
                content=document.content,
                source_type="document_chunk",
                source_locator=document.source_locator
                or {"chunk_id": document.document_id},
                channel="lexical",
                rank=rank,
                raw_score=score,
                tenant_id=document.tenant_id,
                warehouse_ids=document.warehouse_ids,
                required_scopes=document.required_scopes,
                parent_id=document.parent_id,
                neighbor_ids=document.neighbor_ids,
                token_count=max(1, len(_lexical_terms(document.content))),
                metadata=document.metadata,
            )
            for rank, (score, document) in enumerate(scored[:limit], start=1)
        ]
