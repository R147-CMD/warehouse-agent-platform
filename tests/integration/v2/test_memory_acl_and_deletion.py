from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.api.domain.identity import IdentityContext


def identity(
    *,
    tenant: str = "tenant-1",
    scopes: tuple[str, ...] = ("reports.view",),
    warehouses: tuple[str, ...] = ("WH-01",),
) -> IdentityContext:
    return IdentityContext(
        tenant_id=tenant,
        user_id="user-1",
        scopes=scopes,
        warehouse_scope=warehouses,
        authenticated_at=datetime.now(UTC),
    )


async def embedding(text: str) -> tuple[float, ...]:
    lowered = text.lower()
    if "kpi" in lowered or "指标" in lowered or "报表" in lowered:
        return (1.0, 0.0)
    return (0.0, 1.0)


@pytest.mark.asyncio
async def test_loader_applies_acl_expiry_semantic_recall_and_context_budget() -> None:
    from src.api.services.memory_v2.loader import MemoryLoader
    from src.api.services.memory_v2.models import MemoryBudget
    from src.api.services.memory_v2.store import (
        InMemoryMemoryCache,
        InMemoryMemoryIndex,
        InMemoryMemoryStore,
    )
    from src.api.services.memory_v2.writer import MemoryWriter

    index = InMemoryMemoryIndex(embedding)
    cache = InMemoryMemoryCache()
    store = InMemoryMemoryStore(index=index, cache=cache)
    writer = MemoryWriter(store)
    now = datetime.now(UTC)
    visible = await writer.write_candidate(
        identity(),
        memory_key="report.language",
        content="所有经营报表默认使用中文展示",
        memory_type="preference",
        user_confirmed=True,
        source="user",
        required_scopes=("reports.view",),
        warehouse_ids=("WH-01",),
        ttl=timedelta(days=30),
    )
    expired = await writer.write_candidate(
        identity(),
        memory_key="report.old_format",
        content="旧版指标采用红色展示",
        memory_type="preference",
        user_confirmed=True,
        source="user",
        ttl=timedelta(seconds=1),
    )
    assert visible is not None and expired is not None

    context = await MemoryLoader(store).load(
        identity(),
        "经营指标怎么展示",
        budget=MemoryBudget(max_tokens=30, max_items=5, max_recent_turns=2),
        now=now + timedelta(seconds=2),
    )
    cross_tenant = await MemoryLoader(store).load(
        identity(tenant="tenant-2"),
        "经营指标怎么展示",
        now=now + timedelta(seconds=2),
    )
    missing_scope = await MemoryLoader(store).load(
        identity(scopes=()),
        "经营指标怎么展示",
        now=now + timedelta(seconds=2),
    )
    wrong_warehouse = await MemoryLoader(store).load(
        identity(warehouses=("WH-02",)),
        "经营指标怎么展示",
        now=now + timedelta(seconds=2),
    )

    assert [item.memory_id for item in context.long_term_items] == [visible.memory_id]
    assert context.estimated_tokens <= 30
    assert cross_tenant.long_term_items == ()
    assert missing_scope.long_term_items == ()
    assert wrong_warehouse.long_term_items == ()


@pytest.mark.asyncio
async def test_delete_removes_structured_record_vector_projection_and_cache_entry() -> (
    None
):
    from src.api.services.memory_v2.loader import MemoryLoader
    from src.api.services.memory_v2.store import (
        InMemoryMemoryCache,
        InMemoryMemoryIndex,
        InMemoryMemoryStore,
    )
    from src.api.services.memory_v2.writer import MemoryWriter

    index = InMemoryMemoryIndex(embedding)
    cache = InMemoryMemoryCache()
    store = InMemoryMemoryStore(index=index, cache=cache)
    writer = MemoryWriter(store)
    item = await writer.write_candidate(
        identity(),
        memory_key="report.language",
        content="经营报表使用中文",
        memory_type="preference",
        user_confirmed=True,
        source="user",
    )
    assert item is not None

    loaded = await MemoryLoader(store).load(identity(), "KPI display")
    assert loaded.long_term_items
    assert index.contains(item.memory_id)
    assert cache.contains_memory(item.memory_id)

    deleted = await store.delete(identity(), item.memory_id)
    after_delete = await MemoryLoader(store).load(identity(), "KPI display")

    assert deleted is True
    assert after_delete.long_term_items == ()
    assert not index.contains(item.memory_id)
    assert not cache.contains_memory(item.memory_id)


@pytest.mark.asyncio
async def test_new_memory_invalidates_a_previously_cached_empty_query() -> None:
    from src.api.services.memory_v2.loader import MemoryLoader
    from src.api.services.memory_v2.store import (
        InMemoryMemoryCache,
        InMemoryMemoryIndex,
        InMemoryMemoryStore,
    )
    from src.api.services.memory_v2.writer import MemoryWriter

    cache = InMemoryMemoryCache()
    store = InMemoryMemoryStore(
        index=InMemoryMemoryIndex(embedding),
        cache=cache,
    )
    loader = MemoryLoader(store)
    before = await loader.load(identity(), "KPI display")
    assert before.long_term_items == ()

    item = await MemoryWriter(store).write_candidate(
        identity(),
        memory_key="report.language",
        content="经营报表默认使用中文",
        memory_type="preference",
        user_confirmed=True,
        source="user",
    )
    after = await loader.load(identity(), "KPI display")

    assert item is not None
    assert [memory.memory_id for memory in after.long_term_items] == [item.memory_id]
