from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest

from src.api.domain.identity import AccessControl, IdentityContext
from src.api.services.memory_v2.models import ConversationTurn, MemoryItem


class Result:
    def __init__(self, rows):
        self.rows = list(rows)

    async def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    async def fetchall(self):
        rows, self.rows = self.rows, []
        return rows


class Connection:
    def __init__(self, responses):
        self.responses = list(responses)
        self.statements = []

    async def execute(self, statement, parameters=None):
        self.statements.append((str(statement), parameters))
        rows = self.responses.pop(0) if self.responses else []
        return Result(rows)


class Pool:
    def __init__(self, connection):
        self._connection = connection

    @asynccontextmanager
    async def connection(self):
        yield self._connection


def identity() -> IdentityContext:
    return IdentityContext(
        tenant_id="tenant-1",
        user_id="user-1",
        scopes=("reports.view",),
        warehouse_scope=("WH-01",),
        authenticated_at=datetime.now(UTC),
    )


def memory() -> MemoryItem:
    now = datetime(2026, 9, 10, tzinfo=UTC)
    return MemoryItem(
        memory_id="mem-1",
        memory_key="report.language",
        tenant_id="tenant-1",
        user_id="user-1",
        memory_type="preference",
        content="报表默认使用中文",
        source="user",
        source_refs=("run-1",),
        confidence=1.0,
        acl=AccessControl(
            tenant_id="tenant-1",
            warehouse_ids=("WH-01",),
            required_scopes=("reports.view",),
        ),
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(days=90),
    )


def row(item: MemoryItem) -> dict:
    values = item.model_dump(mode="python")
    values["acl"] = item.acl.model_dump(mode="json")
    values["source_refs"] = list(item.source_refs)
    return values


@pytest.mark.asyncio
async def test_postgres_store_upserts_versioned_memory_and_reads_active_scope() -> None:
    from src.api.services.memory_v2.postgres_store import PostgresMemoryStore

    item = memory()
    connection = Connection([[row(item)], [row(item)]])
    store = PostgresMemoryStore(Pool(connection))

    saved = await store.upsert(item)
    active = await store.list_active(identity(), now=datetime(2026, 9, 11, tzinfo=UTC))

    assert saved == item
    assert active == (item,)
    statements = "\n".join(statement for statement, _ in connection.statements)
    assert "ON CONFLICT (memory_id) DO UPDATE" in statements
    assert "version = agent_memory_v2.version + 1" in statements
    assert "deleted_at IS NULL" in statements
    assert "expires_at >" in statements


@pytest.mark.asyncio
async def test_postgres_store_persists_and_reads_short_term_turns() -> None:
    from src.api.services.memory_v2.postgres_store import PostgresMemoryStore

    now = datetime(2026, 9, 10, tzinfo=UTC)
    turn = ConversationTurn(
        turn_id="turn-1",
        tenant_id="tenant-1",
        user_id="user-1",
        conversation_id="conversation-1",
        role="user",
        content="继续查询这个订单",
        created_at=now,
        expires_at=now + timedelta(days=1),
    )
    connection = Connection([[], [turn.model_dump(mode="python")]])
    store = PostgresMemoryStore(Pool(connection))

    await store.append_turn(turn)
    loaded = await store.recent_turns(
        identity(),
        "conversation-1",
        limit=5,
        now=now,
    )

    assert loaded == (turn,)
    assert "ON CONFLICT (turn_id) DO NOTHING" in connection.statements[0][0]


@pytest.mark.asyncio
async def test_memory_store_manager_supports_explicit_local_memory_backend() -> None:
    from src.api.services.memory_v2.manager import MemoryStoreManager
    from src.api.services.memory_v2.store import InMemoryMemoryStore

    manager = MemoryStoreManager(backend="memory")
    await manager.start()

    assert manager.backend == "memory"
    assert isinstance(manager.store, InMemoryMemoryStore)

    await manager.close()
    assert manager.started is False
