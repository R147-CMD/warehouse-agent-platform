from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.api.domain.identity import IdentityContext
from src.api.services.memory_v2.loader import MemoryLoader
from src.api.services.memory_v2.store import InMemoryMemoryStore
from src.api.services.memory_v2.writer import MemoryWriter


def identity(tenant="t1"):
    return IdentityContext(
        tenant_id=tenant,
        user_id="u1",
        authenticated_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_writer_keeps_confirmed_preference_but_rejects_realtime_fact() -> None:
    store = InMemoryMemoryStore()
    writer = MemoryWriter(store)

    preference = await writer.write_candidate(
        identity(),
        content="用户偏好所有 KPI 使用中文展示",
        memory_type="preference",
        user_confirmed=True,
        source="user",
    )
    realtime = await writer.write_candidate(
        identity(),
        content="SKU-1 当前库存 12",
        memory_type="realtime_fact",
        user_confirmed=True,
        source="tool_output",
    )

    assert preference is not None
    assert realtime is None
    loaded = await MemoryLoader(store).load(identity(), "KPI 怎么展示")
    assert [item.memory_id for item in loaded.long_term_items] == [preference.memory_id]


@pytest.mark.asyncio
async def test_loader_enforces_tenant_and_expiry() -> None:
    store = InMemoryMemoryStore()
    writer = MemoryWriter(store)
    item = await writer.write_candidate(
        identity(),
        content="默认仓库是 WH-01",
        memory_type="preference",
        user_confirmed=True,
        source="user",
        ttl=timedelta(seconds=1),
    )

    assert (
        await MemoryLoader(store).load(identity("t2"), "默认仓库")
    ).long_term_items == ()
    expired_at = datetime.now(UTC) + timedelta(seconds=2)
    assert (
        await MemoryLoader(store).load(identity(), "默认仓库", now=expired_at)
    ).long_term_items == ()
