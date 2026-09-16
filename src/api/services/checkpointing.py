"""Checkpoint saver lifecycle management for LangGraph conversations."""

import os

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from src.api.services.database import _get_database_url


class CheckpointManager:
    """Create, own, and close the configured LangGraph checkpoint saver."""

    def __init__(
        self,
        *,
        backend: str | None = None,
        database_url: str | None = None,
        auto_setup: bool | None = None,
        pool_factory=AsyncConnectionPool,
        postgres_saver_factory=AsyncPostgresSaver,
    ) -> None:
        self._configured_backend = backend
        self._database_url = database_url
        self._auto_setup = auto_setup
        self._pool_factory = pool_factory
        self._postgres_saver_factory = postgres_saver_factory
        self._pool = None
        self._saver: BaseCheckpointSaver | None = None
        self._backend: str | None = None
        self._started = False

    @property
    def saver(self) -> BaseCheckpointSaver:
        """Return the active saver once the manager has started."""
        if self._saver is None:
            raise RuntimeError("Checkpoint manager is not started")
        return self._saver

    @property
    def backend(self) -> str:
        """Return the active backend once the manager has started."""
        if self._backend is None:
            raise RuntimeError("Checkpoint manager is not started")
        return self._backend

    @property
    def started(self) -> bool:
        """Whether the manager currently owns an active saver."""
        return self._started

    async def start(self) -> None:
        """Initialize the configured saver exactly once."""
        if self._started:
            return

        backend = (
            self._configured_backend
            or os.getenv("LANGGRAPH_CHECKPOINTER_BACKEND", "postgres")
        ).strip().lower()
        if backend not in {"postgres", "memory"}:
            raise ValueError("LANGGRAPH_CHECKPOINTER_BACKEND must be postgres or memory")

        serde = JsonPlusSerializer(pickle_fallback=False)
        if backend == "memory":
            self._saver = InMemorySaver(serde=serde)
        else:
            database_url = (
                self._database_url
                or os.getenv("LANGGRAPH_CHECKPOINT_DATABASE_URL")
                or _get_database_url()
            )
            self._pool = self._pool_factory(
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
                await self._pool.open()
                await self._pool.wait()
                self._saver = self._postgres_saver_factory(self._pool, serde=serde)
                if self._resolve_auto_setup():
                    await self._saver.setup()
            except BaseException:
                try:
                    await self._pool.close()
                except Exception:
                    pass
                finally:
                    self._pool = None
                    self._saver = None
                raise

        self._backend = backend
        self._started = True

    async def close(self) -> None:
        """Release the PostgreSQL pool, if one was created."""
        if not self._started and self._pool is None:
            return

        pool = self._pool
        try:
            if pool is not None:
                await pool.close()
        finally:
            self._pool = None
            self._saver = None
            self._backend = None
            self._started = False

    async def delete_thread(self, thread_id: str) -> None:
        """Delete persisted checkpoint history for an already-validated thread ID."""
        await self.saver.adelete_thread(thread_id)

    def _resolve_auto_setup(self) -> bool:
        """Resolve the schema-setup flag from explicit configuration or environment."""
        value = self._auto_setup
        if value is None:
            value = os.getenv("LANGGRAPH_CHECKPOINT_AUTO_SETUP", "true")
        if isinstance(value, bool):
            return value

        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        raise ValueError(
            "LANGGRAPH_CHECKPOINT_AUTO_SETUP must be a boolean value "
            "(true/false)"
        )


_checkpoint_manager: CheckpointManager | None = None


def get_checkpoint_manager() -> CheckpointManager:
    """Return the process-wide checkpoint manager."""
    global _checkpoint_manager
    if _checkpoint_manager is None:
        _checkpoint_manager = CheckpointManager()
    return _checkpoint_manager
