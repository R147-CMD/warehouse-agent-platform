"""Lifecycle management for PostgreSQL-backed approval persistence."""

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from src.api.services.database import _get_database_url

from .models import ApprovalRecord, ApprovalStatus
from .repository import ApprovalRepository


logger = logging.getLogger(__name__)


class ApprovalManager:
    """Own the approval repository, connection pool, and expiry worker."""

    def __init__(
        self,
        *,
        database_url: str | None = None,
        auto_setup: bool | str | None = None,
        pool_factory=AsyncConnectionPool,
        repository_factory=ApprovalRepository,
    ) -> None:
        self._database_url = database_url
        self._auto_setup = auto_setup
        self._pool_factory = pool_factory
        self._repository_factory = repository_factory
        self._pool = None
        self._repository: ApprovalRepository | None = None
        self._expiry_task: asyncio.Task[None] | None = None
        self._started = False

    @property
    def repository(self) -> ApprovalRepository:
        """Return the active repository once the manager has started."""

        if not self._started or self._repository is None:
            raise RuntimeError("Approval manager is not started")
        return self._repository

    @property
    def started(self) -> bool:
        """Whether the manager currently owns an open approval pool."""

        return self._started

    async def start(self) -> None:
        """Open the pool and initialize the repository exactly once."""

        if self._started:
            return

        database_url = self._resolve_database_url()
        pool = self._pool_factory(
            conninfo=database_url,
            min_size=1,
            max_size=3,
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
            repository = self._repository_factory(pool)
            if self._resolve_auto_setup():
                await repository.setup()
        except BaseException:
            try:
                await pool.close()
            except BaseException:
                pass
            finally:
                self._pool = None
                self._repository = None
                self._started = False
            raise

        self._pool = pool
        self._repository = repository
        self._started = True

    async def close(self) -> None:
        """Stop expiry processing first, then release the connection pool."""

        expiry_task = self._expiry_task
        self._expiry_task = None
        if expiry_task is not None:
            expiry_task.cancel()
            if expiry_task is not asyncio.current_task():
                try:
                    await expiry_task
                except asyncio.CancelledError:
                    pass

        pool = self._pool
        try:
            if pool is not None:
                await pool.close()
        finally:
            self._pool = None
            self._repository = None
            self._started = False

    def start_expiry_worker(
        self,
        handler: Callable[[ApprovalRecord], Awaitable[None]],
    ) -> None:
        """Start the single background worker that propagates expiry records."""

        repository = self.repository
        existing_task = self._expiry_task
        if existing_task is not None and not existing_task.done():
            return

        interval = self._resolve_sweep_seconds()
        self._expiry_task = asyncio.create_task(
            self._run_expiry_worker(repository, handler, interval),
            name="langgraph-approval-expiry",
        )

    async def _run_expiry_worker(
        self,
        repository: ApprovalRepository,
        handler: Callable[[ApprovalRecord], Awaitable[None]],
        interval: int,
    ) -> None:
        try:
            while True:
                await asyncio.sleep(interval)
                try:
                    expired_records = await repository.claim_expired()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.error("Approval expiry sweep failed")
                    continue

                for record in expired_records:
                    try:
                        await handler(record)
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        logger.error(
                            "Approval expiry handler failed for approval %s",
                            record.approval_id,
                        )
                        await self._mark_worker_failure_if_safe(repository, record)
        except asyncio.CancelledError:
            return

    @staticmethod
    async def _mark_worker_failure_if_safe(
        repository: ApprovalRepository,
        record: ApprovalRecord,
    ) -> None:
        try:
            current = await repository.get(record.approval_id)
            if current is not None and current.status is ApprovalStatus.EXECUTING:
                await repository.mark_failed(
                    record.approval_id,
                    "Approval expiry handler failed",
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.error(
                "Approval expiry failure state could not be recorded for approval %s",
                record.approval_id,
            )

    def _resolve_database_url(self) -> str:
        configured = _nonempty(self._database_url)
        if configured is not None:
            return configured

        approval_url = _nonempty(os.getenv("LANGGRAPH_APPROVAL_DATABASE_URL"))
        if approval_url is not None:
            return approval_url

        checkpoint_url = _nonempty(os.getenv("LANGGRAPH_CHECKPOINT_DATABASE_URL"))
        if checkpoint_url is not None:
            return checkpoint_url
        return _get_database_url()

    def _resolve_auto_setup(self) -> bool:
        value = self._auto_setup
        if value is None:
            value = os.getenv("LANGGRAPH_APPROVAL_AUTO_SETUP", "true")
        if isinstance(value, bool):
            return value

        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        raise ValueError(
            "LANGGRAPH_APPROVAL_AUTO_SETUP must be a boolean value (true/false)"
        )

    @staticmethod
    def _resolve_sweep_seconds() -> int:
        raw_value = os.getenv("LANGGRAPH_APPROVAL_SWEEP_SECONDS", "60").strip()
        try:
            value = int(raw_value)
        except ValueError as error:
            raise ValueError(
                "LANGGRAPH_APPROVAL_SWEEP_SECONDS must be a positive integer"
            ) from error
        if value <= 0:
            raise ValueError(
                "LANGGRAPH_APPROVAL_SWEEP_SECONDS must be a positive integer"
            )
        return value


def _nonempty(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


_approval_manager: ApprovalManager | None = None


def get_approval_manager() -> ApprovalManager:
    """Return the process-wide approval manager."""

    global _approval_manager
    if _approval_manager is None:
        _approval_manager = ApprovalManager()
    return _approval_manager
