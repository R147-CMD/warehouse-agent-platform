from __future__ import annotations

import pytest

from src.api.services.execution.manager import ExecutionStoreManager
from src.api.services.execution.postgres_store import PostgresExecutionStore
from src.api.services.execution.store import InMemoryExecutionStore


class Pool:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.opened = False
        self.waited = False
        self.closed = False

    async def open(self):
        self.opened = True

    async def wait(self):
        self.waited = True

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_manager_uses_in_memory_store_only_when_explicitly_configured() -> None:
    manager = ExecutionStoreManager(backend="memory")

    await manager.start()

    assert isinstance(manager.store, InMemoryExecutionStore)
    assert manager.backend == "memory"
    await manager.close()


@pytest.mark.asyncio
async def test_manager_owns_postgres_pool_lifecycle() -> None:
    pools = []

    def factory(**kwargs):
        pool = Pool(**kwargs)
        pools.append(pool)
        return pool

    manager = ExecutionStoreManager(
        backend="postgres",
        database_url="postgresql://warehouse:secret@db/warehouse",
        pool_factory=factory,
    )

    await manager.start()

    assert isinstance(manager.store, PostgresExecutionStore)
    assert pools[0].opened is True
    assert pools[0].waited is True
    assert pools[0].kwargs["min_size"] == 1
    assert pools[0].kwargs["max_size"] == 5

    await manager.close()
    assert pools[0].closed is True
