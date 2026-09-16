"""Query-adaptive Hybrid RAG retrieval pipeline."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence

from src.api.domain.identity import IdentityContext

from .context_builder import ContextBuilder
from .contracts import (
    QueryEnvelope,
    RetrievalCandidate,
    RetrievalChannel,
    RetrievalResult,
)
from .fusion import reciprocal_rank_fusion
from .reranker import CrossEncoderReranker

SearchCallable = Callable[..., Awaitable[Sequence[RetrievalCandidate]]]


class RetrievalPipeline:
    def __init__(
        self,
        *,
        lexical_search: SearchCallable | None = None,
        dense_search: SearchCallable | None = None,
        structured_search: SearchCallable | None = None,
        reranker: CrossEncoderReranker | None = None,
        context_builder: ContextBuilder | None = None,
        candidate_limit: int = 50,
    ) -> None:
        self._searchers: dict[RetrievalChannel, SearchCallable | None] = {
            "structured": structured_search,
            "lexical": lexical_search,
            "dense": dense_search,
        }
        self.reranker = reranker or CrossEncoderReranker()
        self.context_builder = context_builder or ContextBuilder()
        self.candidate_limit = candidate_limit

    async def retrieve(
        self, query: QueryEnvelope, identity: IdentityContext
    ) -> RetrievalResult:
        channels = self._channels_for(query)
        filters: dict[str, object] = {
            **query.filters,
            "tenant_id": identity.tenant_id,
            "warehouse_ids": identity.warehouse_scope,
        }

        async def call(channel: RetrievalChannel) -> list[RetrievalCandidate]:
            search = self._searchers[channel]
            if search is None:
                raise RuntimeError(f"{channel} provider is not configured")
            text = (
                query.semantic_queries[0]
                if channel == "dense" and query.semantic_queries
                else query.normalized_query
            )
            return list(await search(text, filters=filters, limit=self.candidate_limit))

        results = await asyncio.gather(
            *(call(channel) for channel in channels), return_exceptions=True
        )
        rankings: list[list[RetrievalCandidate]] = []
        degraded: list[RetrievalChannel] = []
        errors: dict[str, str] = {}
        for channel, result in zip(channels, results, strict=True):
            if isinstance(result, BaseException):
                degraded.append(channel)
                errors[channel] = f"{type(result).__name__}: {result}"
            else:
                rankings.append(self._validate_acl(result, identity))
        fused = reciprocal_rank_fusion(rankings)
        reranked, reranker_degraded = await self.reranker.rerank(
            query.normalized_query, fused
        )
        if reranker_degraded:
            errors["reranker"] = "reranker unavailable; RRF order used"
        context = self.context_builder.build(reranked)
        if not rankings:
            status = "failed"
        elif degraded or reranker_degraded:
            status = "partial"
        else:
            status = "succeeded"
        return RetrievalResult(
            status=status,
            context=context,
            candidates=tuple(reranked),
            degraded_channels=tuple(degraded),
            errors=errors,
        )

    @staticmethod
    def _channels_for(query: QueryEnvelope) -> tuple[RetrievalChannel, ...]:
        if query.query_type == "structured_fact":
            return ("structured",)
        if query.query_type in {"document_knowledge", "hybrid", "multi_hop"}:
            return ("lexical", "dense")
        return ("structured", "lexical")

    @staticmethod
    def _validate_acl(
        candidates: Sequence[RetrievalCandidate], identity: IdentityContext
    ) -> list[RetrievalCandidate]:
        scopes = set(identity.scopes)
        warehouses = set(identity.warehouse_scope)
        return [
            candidate
            for candidate in candidates
            if candidate.tenant_id == identity.tenant_id
            and set(candidate.required_scopes).issubset(scopes)
            and (
                not candidate.warehouse_ids
                or bool(set(candidate.warehouse_ids) & warehouses)
            )
        ]
