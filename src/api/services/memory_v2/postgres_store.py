"""PostgreSQL implementation for conversation and long-term memory."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from psycopg.types.json import Jsonb

from src.api.domain.identity import IdentityContext

from .models import ConversationTurn, MemoryItem
from .store import MemoryCache, MemoryIndex, can_read_memory


class PostgresMemoryStore:
    def __init__(
        self,
        pool: Any,
        *,
        index: MemoryIndex | None = None,
        cache: MemoryCache | None = None,
    ) -> None:
        self._pool = pool
        self.index = index
        self.cache = cache

    async def upsert(self, item: MemoryItem) -> MemoryItem:
        statement = """
            INSERT INTO agent_memory_v2 (
                memory_id, memory_key, tenant_id, user_id, memory_type,
                content, source, source_refs, confidence, acl, version,
                created_at, updated_at, expires_at, deleted_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            )
            ON CONFLICT (memory_id) DO UPDATE SET
                content = EXCLUDED.content,
                source = EXCLUDED.source,
                source_refs = EXCLUDED.source_refs,
                confidence = EXCLUDED.confidence,
                acl = EXCLUDED.acl,
                version = agent_memory_v2.version + 1,
                updated_at = EXCLUDED.updated_at,
                expires_at = EXCLUDED.expires_at,
                deleted_at = NULL
            WHERE agent_memory_v2.tenant_id = EXCLUDED.tenant_id
              AND agent_memory_v2.user_id = EXCLUDED.user_id
              AND agent_memory_v2.memory_key = EXCLUDED.memory_key
            RETURNING *
        """
        parameters = (
            item.memory_id,
            item.memory_key,
            item.tenant_id,
            item.user_id,
            item.memory_type,
            item.content,
            item.source,
            Jsonb(list(item.source_refs)),
            item.confidence,
            Jsonb(item.acl.model_dump(mode="json")),
            item.version,
            item.created_at,
            item.updated_at,
            item.expires_at,
            item.deleted_at,
        )
        async with self._pool.connection() as connection:
            result = await connection.execute(statement, parameters)
            row = await result.fetchone()
        if row is None:
            raise ValueError("memory ID belongs to another scope")
        saved = _memory_from_row(row)
        if self.index is not None:
            await self.index.upsert(saved)
        if self.cache is not None:
            await self.cache.invalidate_scope(saved.tenant_id, saved.user_id)
        return saved

    async def get(self, identity: IdentityContext, memory_id: str) -> MemoryItem | None:
        async with self._pool.connection() as connection:
            result = await connection.execute(
                """
                SELECT * FROM agent_memory_v2
                WHERE memory_id = %s AND tenant_id = %s AND user_id = %s
                  AND deleted_at IS NULL
                """,
                (memory_id, identity.tenant_id, identity.user_id),
            )
            row = await result.fetchone()
        if row is None:
            return None
        item = _memory_from_row(row)
        return item if can_read_memory(item, identity) else None

    async def get_by_key(
        self, identity: IdentityContext, memory_key: str
    ) -> MemoryItem | None:
        async with self._pool.connection() as connection:
            result = await connection.execute(
                """
                SELECT * FROM agent_memory_v2
                WHERE tenant_id = %s AND user_id = %s AND memory_key = %s
                  AND deleted_at IS NULL
                """,
                (identity.tenant_id, identity.user_id, memory_key),
            )
            row = await result.fetchone()
        if row is None:
            return None
        item = _memory_from_row(row)
        return item if can_read_memory(item, identity) else None

    async def list_active(
        self, identity: IdentityContext, *, now: datetime
    ) -> tuple[MemoryItem, ...]:
        async with self._pool.connection() as connection:
            result = await connection.execute(
                """
                SELECT * FROM agent_memory_v2
                WHERE tenant_id = %s AND user_id = %s
                  AND deleted_at IS NULL
                  AND (expires_at IS NULL OR expires_at > %s)
                ORDER BY memory_key, memory_id
                """,
                (identity.tenant_id, identity.user_id, now),
            )
            rows = await result.fetchall()
        return tuple(
            item
            for row in rows
            if can_read_memory(item := _memory_from_row(row), identity)
        )

    async def delete(self, identity: IdentityContext, memory_id: str) -> bool:
        deleted_at = datetime.now(UTC)
        async with self._pool.connection() as connection:
            result = await connection.execute(
                """
                UPDATE agent_memory_v2
                SET deleted_at = %s, updated_at = %s
                WHERE memory_id = %s AND tenant_id = %s AND user_id = %s
                  AND deleted_at IS NULL
                RETURNING memory_id
                """,
                (
                    deleted_at,
                    deleted_at,
                    memory_id,
                    identity.tenant_id,
                    identity.user_id,
                ),
            )
            row = await result.fetchone()
        if row is None:
            return False
        if self.index is not None:
            await self.index.delete(memory_id)
        if self.cache is not None:
            await self.cache.invalidate_memory(memory_id)
        return True

    async def append_turn(self, turn: ConversationTurn) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(
                """
                INSERT INTO conversation_turns_v2 (
                    turn_id, tenant_id, user_id, conversation_id, role,
                    content, created_at, expires_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (turn_id) DO NOTHING
                """,
                (
                    turn.turn_id,
                    turn.tenant_id,
                    turn.user_id,
                    turn.conversation_id,
                    turn.role,
                    turn.content,
                    turn.created_at,
                    turn.expires_at,
                ),
            )

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
        async with self._pool.connection() as connection:
            result = await connection.execute(
                """
                SELECT * FROM conversation_turns_v2
                WHERE tenant_id = %s AND user_id = %s AND conversation_id = %s
                  AND expires_at > %s
                ORDER BY created_at DESC, turn_id DESC
                LIMIT %s
                """,
                (
                    identity.tenant_id,
                    identity.user_id,
                    conversation_id,
                    now,
                    limit,
                ),
            )
            rows = await result.fetchall()
        turns = [ConversationTurn.model_validate(row) for row in rows]
        turns.reverse()
        return tuple(turns)


def _memory_from_row(row: dict[str, Any]) -> MemoryItem:
    values = dict(row)
    values["source_refs"] = tuple(values.get("source_refs") or ())
    return MemoryItem.model_validate(values)
