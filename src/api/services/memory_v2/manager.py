"""Lifecycle manager for the V2 memory store."""

from __future__ import annotations

import os

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from src.api.services.database import _get_database_url

from .postgres_store import PostgresMemoryStore
from .store import InMemoryMemoryStore, MemoryStore


class MemoryStoreManager:
    def __init__(
        self,
        *,
        backend: str | None = None,
        database_url: str | None = None,
        pool_factory=AsyncConnectionPool,
    ) -> None:
        self._configured_backend = backend
        self._database_url = database_url
        self._pool_factory = pool_factory
        self._pool = None
        self._store: MemoryStore | None = None
        self._backend: str | None = None
        self._started = False

    @property
    def store(self) -> MemoryStore:
        if self._store is None:
            raise RuntimeError("memory store manager is not started")
        return self._store

    @property
    def backend(self) -> str:
        if self._backend is None:
            raise RuntimeError("memory store manager is not started")
        return self._backend

    @property
    def started(self) -> bool:
        return self._started

    async def start(self) -> None:
        if self._started:
            return
        backend = (
            (
                self._configured_backend
                or os.getenv("WAREHOUSE_MEMORY_STORE_BACKEND", "postgres")
            )
            .strip()
            .lower()
        )
        if backend not in {"postgres", "memory"}:
            raise ValueError(
                "WAREHOUSE_MEMORY_STORE_BACKEND must be postgres or memory"
            )
        if backend == "memory":
            self._store = InMemoryMemoryStore()
        else:
            database_url = (
                self._database_url
                or os.getenv("WAREHOUSE_MEMORY_DATABASE_URL")
                or os.getenv("LANGGRAPH_CHECKPOINT_DATABASE_URL")
                or _get_database_url()
            )
            pool = self._pool_factory(
                conninfo=database_url,
                min_size=1,
                max_size=5,
                kwargs={
                    "autocommit": True,
                    "prepare_threshold": 0,
                    "row_factory": dict_row,
                },
                open=False,
            )
            try:
                await pool.open()
                await pool.wait()
            except BaseException:
                try:
                    await pool.close()
                finally:
                    raise
            self._pool = pool
            self._store = PostgresMemoryStore(pool)
        self._backend = backend
        self._started = True

    async def close(self) -> None:
        pool = self._pool
        try:
            if pool is not None:
                await pool.close()
        finally:
            self._pool = None
            self._store = None
            self._backend = None
            self._started = False


_manager: MemoryStoreManager | None = None


def get_memory_store_manager() -> MemoryStoreManager:
    global _manager
    if _manager is None:
        _manager = MemoryStoreManager()
    return _manager
