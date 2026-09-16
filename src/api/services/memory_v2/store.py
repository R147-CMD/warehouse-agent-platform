"""Memory persistence, vector projection and cache contracts."""

from __future__ import annotations

import inspect
import math
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Protocol

from src.api.domain.identity import IdentityContext

from .models import ConversationTurn, MemoryItem

EmbeddingProvider = Callable[[str], tuple[float, ...] | Awaitable[tuple[float, ...]]]


def can_read_memory(item: MemoryItem, identity: IdentityContext) -> bool:
    acl = item.acl
    return (
        item.deleted_at is None
        and item.tenant_id == identity.tenant_id
        and item.user_id == identity.user_id
        and acl.tenant_id == identity.tenant_id
        and set(acl.required_scopes).issubset(identity.scopes)
        and (
            not acl.warehouse_ids
            or bool(set(acl.warehouse_ids) & set(identity.warehouse_scope))
        )
    )


class MemoryIndex(Protocol):
    async def upsert(self, item: MemoryItem) -> None: ...

    async def search(
        self, identity: IdentityContext, query: str, *, limit: int
    ) -> tuple[tuple[str, float], ...]: ...

    async def delete(self, memory_id: str) -> None: ...


class MemoryCache(Protocol):
    async def get(self, key: str) -> tuple[str, ...] | None: ...

    async def put(self, key: str, memory_ids: tuple[str, ...]) -> None: ...

    async def invalidate_memory(self, memory_id: str) -> None: ...

    async def invalidate_scope(self, tenant_id: str, user_id: str) -> None: ...


class MemoryStore(Protocol):
    index: MemoryIndex | None
    cache: MemoryCache | None

    async def upsert(self, item: MemoryItem) -> MemoryItem: ...

    async def get(
        self, identity: IdentityContext, memory_id: str
    ) -> MemoryItem | None: ...

    async def get_by_key(
        self, identity: IdentityContext, memory_key: str
    ) -> MemoryItem | None: ...

    async def list_active(
        self, identity: IdentityContext, *, now: datetime
    ) -> tuple[MemoryItem, ...]: ...

    async def delete(self, identity: IdentityContext, memory_id: str) -> bool: ...

    async def append_turn(self, turn: ConversationTurn) -> None: ...

    async def recent_turns(
        self,
        identity: IdentityContext,
        conversation_id: str,
        *,
        limit: int,
        now: datetime,
    ) -> tuple[ConversationTurn, ...]: ...


class InMemoryMemoryIndex:
    """Small cosine index used by local development and contract tests."""

    def __init__(self, embed: EmbeddingProvider) -> None:
        self._embed = embed
        self._vectors: dict[str, tuple[float, ...]] = {}
        self._items: dict[str, MemoryItem] = {}

    async def _vector(self, text: str) -> tuple[float, ...]:
        value = self._embed(text)
        if inspect.isawaitable(value):
            value = await value
        return tuple(float(item) for item in value)

    async def upsert(self, item: MemoryItem) -> None:
        self._vectors[item.memory_id] = await self._vector(item.content)
        self._items[item.memory_id] = item

    async def search(
        self, identity: IdentityContext, query: str, *, limit: int
    ) -> tuple[tuple[str, float], ...]:
        query_vector = await self._vector(query)
        hits = []
        for memory_id, vector in self._vectors.items():
            item = self._items[memory_id]
            if not can_read_memory(item, identity):
                continue
            score = _cosine(query_vector, vector)
            if score > 0:
                hits.append((memory_id, score))
        hits.sort(key=lambda item: (-item[1], item[0]))
        return tuple(hits[:limit])

    async def delete(self, memory_id: str) -> None:
        self._vectors.pop(memory_id, None)
        self._items.pop(memory_id, None)

    def contains(self, memory_id: str) -> bool:
        return memory_id in self._vectors


class InMemoryMemoryCache:
    def __init__(self) -> None:
        self._values: dict[str, tuple[str, ...]] = {}

    async def get(self, key: str) -> tuple[str, ...] | None:
        return self._values.get(key)

    async def put(self, key: str, memory_ids: tuple[str, ...]) -> None:
        self._values[key] = memory_ids

    async def invalidate_memory(self, memory_id: str) -> None:
        self._values = {
            key: ids for key, ids in self._values.items() if memory_id not in ids
        }

    async def invalidate_scope(self, tenant_id: str, user_id: str) -> None:
        prefix = f"memory:{tenant_id}:{user_id}:"
        self._values = {
            key: ids for key, ids in self._values.items() if not key.startswith(prefix)
        }

    def contains_memory(self, memory_id: str) -> bool:
        return any(memory_id in ids for ids in self._values.values())


class InMemoryMemoryStore:
    def __init__(
        self,
        *,
        index: MemoryIndex | None = None,
        cache: MemoryCache | None = None,
    ) -> None:
        self.index = index
        self.cache = cache
        self._items: dict[str, MemoryItem] = {}
        self._turns: dict[str, ConversationTurn] = {}

    async def upsert(self, item: MemoryItem) -> MemoryItem:
        existing = self._items.get(item.memory_id)
        if existing is not None and (
            existing.tenant_id != item.tenant_id
            or existing.user_id != item.user_id
            or existing.memory_key != item.memory_key
        ):
            raise ValueError("memory ID belongs to another scope")
        self._items[item.memory_id] = item
        if self.index is not None:
            await self.index.upsert(item)
        if self.cache is not None:
            await self.cache.invalidate_scope(item.tenant_id, item.user_id)
        return item

    async def get(self, identity: IdentityContext, memory_id: str) -> MemoryItem | None:
        item = self._items.get(memory_id)
        return item if item is not None and can_read_memory(item, identity) else None

    async def get_by_key(
        self, identity: IdentityContext, memory_key: str
    ) -> MemoryItem | None:
        return next(
            (
                item
                for item in self._items.values()
                if item.memory_key == memory_key and can_read_memory(item, identity)
            ),
            None,
        )

    async def list_active(
        self, identity: IdentityContext, *, now: datetime
    ) -> tuple[MemoryItem, ...]:
        return tuple(
            sorted(
                (
                    item
                    for item in self._items.values()
                    if can_read_memory(item, identity)
                    and (item.expires_at is None or item.expires_at > now)
                ),
                key=lambda item: (item.memory_key, item.memory_id),
            )
        )

    async def delete(self, identity: IdentityContext, memory_id: str) -> bool:
        item = await self.get(identity, memory_id)
        if item is None:
            return False
        deleted = item.model_copy(
            update={"deleted_at": datetime.now(item.created_at.tzinfo)}
        )
        self._items[memory_id] = deleted
        if self.index is not None:
            await self.index.delete(memory_id)
        if self.cache is not None:
            await self.cache.invalidate_memory(memory_id)
        return True

    async def append_turn(self, turn: ConversationTurn) -> None:
        existing = self._turns.get(turn.turn_id)
        if existing is not None and existing != turn:
            raise ValueError("turn ID already exists with different content")
        self._turns.setdefault(turn.turn_id, turn)

    async def recent_turns(
        self,
        identity: IdentityContext,
        conversation_id: str,
        *,
        limit: int,
        now: datetime,
    ) -> tuple[ConversationTurn, ...]:
        if limit <= 0:
            return ()
        turns = [
            item
            for item in self._turns.values()
            if item.tenant_id == identity.tenant_id
            and item.user_id == identity.user_id
            and item.conversation_id == conversation_id
            and item.expires_at > now
        ]
        turns.sort(key=lambda item: (item.created_at, item.turn_id))
        return tuple(turns[-limit:])


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    denominator = math.sqrt(sum(item * item for item in left)) * math.sqrt(
        sum(item * item for item in right)
    )
    if denominator == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / denominator
