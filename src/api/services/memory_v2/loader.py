"""ACL-first memory retrieval with semantic fallback and context budgeting."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from hashlib import sha256

from src.api.domain.identity import IdentityContext

from .models import MemoryBudget, MemoryContext, MemoryItem
from .store import MemoryStore


class MemoryLoader:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    async def load(
        self,
        identity: IdentityContext,
        query: str,
        *,
        budget: MemoryBudget | None = None,
        conversation_id: str | None = None,
        now: datetime | None = None,
    ) -> MemoryContext:
        budget = budget or MemoryBudget()
        now = now or datetime.now(UTC)
        recent_turns = (
            await self.store.recent_turns(
                identity,
                conversation_id,
                limit=budget.max_recent_turns,
                now=now,
            )
            if conversation_id and budget.max_recent_turns
            else ()
        )
        items = await self._ranked_items(identity, query, budget, now)

        selected_turns = []
        selected_items = []
        used_tokens = 0
        truncated = False
        for turn in recent_turns:
            cost = _estimated_tokens(turn.content)
            if used_tokens + cost > budget.max_tokens:
                truncated = True
                continue
            selected_turns.append(turn)
            used_tokens += cost
        for item in items:
            cost = _estimated_tokens(item.content)
            if used_tokens + cost > budget.max_tokens:
                truncated = True
                continue
            selected_items.append(item)
            used_tokens += cost

        return MemoryContext(
            recent_turns=tuple(selected_turns),
            long_term_items=tuple(selected_items),
            estimated_tokens=used_tokens,
            truncated=truncated,
        )

    async def _ranked_items(
        self,
        identity: IdentityContext,
        query: str,
        budget: MemoryBudget,
        now: datetime,
    ) -> tuple[MemoryItem, ...]:
        cache_key = _cache_key(identity, query, budget)
        if self.store.cache is not None:
            cached_ids = await self.store.cache.get(cache_key)
            if cached_ids is not None:
                cached_items = []
                for memory_id in cached_ids:
                    item = await self.store.get(identity, memory_id)
                    if (
                        item is not None
                        and (item.expires_at is None or item.expires_at > now)
                        and item.confidence >= budget.min_confidence
                    ):
                        cached_items.append(item)
                return tuple(cached_items)

        active = [
            item
            for item in await self.store.list_active(identity, now=now)
            if item.confidence >= budget.min_confidence
        ]
        query_terms = _terms(query)
        scores: dict[str, float] = {}
        for item in active:
            overlap = len(query_terms & _terms(item.content))
            if overlap:
                scores[item.memory_id] = 2.0 * overlap + item.confidence

        if self.store.index is not None and budget.max_items:
            for memory_id, score in await self.store.index.search(
                identity, query, limit=max(1, budget.max_items * 2)
            ):
                scores[memory_id] = max(scores.get(memory_id, 0.0), score)

        by_id = {item.memory_id: item for item in active}
        ranked = [by_id[memory_id] for memory_id in scores if memory_id in by_id]
        ranked.sort(
            key=lambda item: (
                -scores[item.memory_id],
                -item.confidence,
                item.memory_id,
            )
        )
        result = tuple(ranked[: budget.max_items])
        if self.store.cache is not None:
            await self.store.cache.put(
                cache_key, tuple(item.memory_id for item in result)
            )
        return result


def _terms(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+|[一-鿿]", text.lower()))


def _estimated_tokens(text: str) -> int:
    cjk = len(re.findall(r"[一-鿿]", text))
    non_cjk = max(0, len(text) - cjk)
    return max(1, cjk + (non_cjk + 3) // 4)


def _cache_key(identity: IdentityContext, query: str, budget: MemoryBudget) -> str:
    digest = sha256(query.strip().lower().encode("utf-8")).hexdigest()[:20]
    scope = ",".join(sorted(identity.scopes))
    warehouses = ",".join(sorted(identity.warehouse_scope))
    return (
        f"memory:{identity.tenant_id}:{identity.user_id}:{scope}:{warehouses}:"
        f"{budget.max_items}:{budget.min_confidence}:{digest}"
    )
