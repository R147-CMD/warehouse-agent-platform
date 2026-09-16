"""Lifecycle management and business helpers for agent run tracking."""

import asyncio
import logging
import os
from typing import Any
from uuid import UUID

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from src.api.services.database import _get_database_url

from .models import (
    RunCancelled,
    RunEventRecord,
    RunEventSeverity,
    RunEventType,
    RunRecord,
    RunStatus,
    RunUpdate,
)
from .repository import RunRepository


logger = logging.getLogger(__name__)


class RunManager:
    """Own the run repository, connection pool, and cleanup worker."""

    def __init__(
        self,
        *,
        database_url: str | None = None,
        auto_setup: bool | str | None = None,
        pool_factory=AsyncConnectionPool,
        repository_factory=RunRepository,
    ) -> None:
        self._database_url = database_url
        self._auto_setup = auto_setup
        self._pool_factory = pool_factory
        self._repository_factory = repository_factory
        self._pool = None
        self._repository: RunRepository | None = None
        self._cleanup_task: asyncio.Task[None] | None = None
        self._started = False

    @property
    def repository(self) -> RunRepository:
        """Return the active repository after startup."""

        if not self._started or self._repository is None:
            raise RuntimeError("Run manager is not started")
        return self._repository

    @property
    def started(self) -> bool:
        """Whether the manager owns an open pool."""

        return self._started

    async def start(self) -> None:
        """Open the pool and initialize tables exactly once."""

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
            self._pool = None
            self._repository = None
            self._started = False
            raise

        self._pool = pool
        self._repository = repository
        self._started = True

    async def close(self) -> None:
        """Stop cleanup processing and release the connection pool."""

        cleanup_task = self._cleanup_task
        self._cleanup_task = None
        if cleanup_task is not None:
            cleanup_task.cancel()
            if cleanup_task is not asyncio.current_task():
                try:
                    await cleanup_task
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

    async def emit_event(
        self,
        *,
        run_id: UUID,
        event_type: RunEventType,
        message: str,
        severity: RunEventSeverity = RunEventSeverity.INFO,
        agent_name: str | None = None,
        tool_name: str | None = None,
        approval_id: UUID | None = None,
        checkpoint_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> RunEventRecord:
        """Append one standard timeline event."""

        return await self.repository.append_event(
            run_id=run_id,
            event_type=event_type,
            severity=severity,
            message=message,
            agent_name=agent_name,
            tool_name=tool_name,
            approval_id=approval_id,
            checkpoint_id=checkpoint_id,
            payload=payload,
        )

    async def mark_running(self, run_id: UUID) -> RunRecord:
        """Mark a run as active and append a start event."""

        record = await self.repository.mark_started(run_id)
        await self.emit_event(
            run_id=run_id,
            event_type=RunEventType.RUN_STARTED,
            message="任务开始执行",
        )
        return record

    async def mark_waiting_approval(
        self,
        run_id: UUID,
        approval_id: UUID | None = None,
    ) -> RunRecord:
        """Mark a run as waiting for human approval."""

        record = await self.repository.mark_waiting_approval(
            run_id,
            approval_id=approval_id,
        )
        await self.emit_event(
            run_id=run_id,
            event_type=RunEventType.RUN_WAITING_APPROVAL,
            message="任务等待人工审批",
            approval_id=approval_id,
        )
        return record

    async def mark_completed(
        self,
        run_id: UUID,
        result_summary: str | None = None,
    ) -> RunRecord:
        """Mark a run as completed."""

        record = await self.repository.update_run(
            run_id,
            RunUpdate(
                status=RunStatus.COMPLETED,
                result_summary=_safe_summary(result_summary),
                current_agent=None,
                current_tool=None,
            ),
        )
        await self.emit_event(
            run_id=run_id,
            event_type=RunEventType.RUN_COMPLETED,
            message="任务已完成",
            payload={"result_summary": record.result_summary},
        )
        return record

    async def mark_failed(
        self,
        run_id: UUID,
        error: Exception | str,
        error_code: str | None = None,
    ) -> RunRecord:
        """Mark a run as failed with a credential-safe error summary."""

        summary = _safe_summary(f"{type(error).__name__}: {error}" if isinstance(error, Exception) else str(error))
        record = await self.repository.update_run(
            run_id,
            RunUpdate(
                status=RunStatus.FAILED,
                error_code=error_code or (
                    type(error).__name__ if isinstance(error, Exception) else "RunError"
                ),
                error_message=summary,
                current_agent=None,
                current_tool=None,
            ),
        )
        await self.emit_event(
            run_id=run_id,
            event_type=RunEventType.RUN_FAILED,
            severity=RunEventSeverity.ERROR,
            message="任务执行失败",
            payload={"error": summary},
        )
        return record

    async def mark_cancelled(
        self,
        run_id: UUID,
        reason: str | None = None,
    ) -> RunRecord:
        """Mark a run as cooperatively cancelled."""

        record = await self.repository.update_run(
            run_id,
            RunUpdate(
                status=RunStatus.CANCELLED,
                result_summary=_safe_summary(reason) or "任务已取消",
                current_agent=None,
                current_tool=None,
            ),
        )
        await self.emit_event(
            run_id=run_id,
            event_type=RunEventType.RUN_CANCELLED,
            severity=RunEventSeverity.WARNING,
            message="任务已取消",
            payload={"reason": reason},
        )
        return record

    async def request_cancel(
        self,
        run_id: UUID,
        reason: str | None = None,
    ) -> RunRecord:
        """Request cooperative cancellation for a run."""

        record = await self.repository.mark_cancel_requested(run_id)
        await self.emit_event(
            run_id=run_id,
            event_type=RunEventType.RUN_CANCEL_REQUESTED,
            severity=RunEventSeverity.WARNING,
            message="已请求取消任务",
            payload={"reason": reason},
        )
        return record

    async def ensure_not_cancelled(self, run_id: UUID) -> None:
        """Raise when the run has a pending or completed cancellation."""

        record = await self.repository.get_run(run_id)
        if record is not None and record.status in {
            RunStatus.CANCEL_REQUESTED,
            RunStatus.CANCELLED,
        }:
            raise RunCancelled(run_id)

    def start_cleanup_worker(self) -> None:
        """Start a lightweight retention cleanup worker."""

        repository = self.repository
        existing_task = self._cleanup_task
        if existing_task is not None and not existing_task.done():
            return

        interval = self._resolve_sweep_seconds()
        self._cleanup_task = asyncio.create_task(
            self._run_cleanup_worker(repository, interval),
            name="agent-run-cleanup",
        )

    async def _run_cleanup_worker(
        self,
        repository: RunRepository,
        interval: int,
    ) -> None:
        try:
            while True:
                await asyncio.sleep(interval)
                try:
                    await repository.delete_expired()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.error("Agent run cleanup sweep failed")
        except asyncio.CancelledError:
            return

    def _resolve_database_url(self) -> str:
        configured = _nonempty(self._database_url)
        if configured is not None:
            return configured

        run_url = _nonempty(os.getenv("AGENT_RUN_DATABASE_URL"))
        if run_url is not None:
            return run_url

        checkpoint_url = _nonempty(os.getenv("LANGGRAPH_CHECKPOINT_DATABASE_URL"))
        if checkpoint_url is not None:
            return checkpoint_url
        return _get_database_url()

    def _resolve_auto_setup(self) -> bool:
        value = self._auto_setup
        if value is None:
            value = os.getenv("AGENT_RUN_AUTO_SETUP", "true")
        if isinstance(value, bool):
            return value

        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        raise ValueError("AGENT_RUN_AUTO_SETUP must be a boolean value")

    @staticmethod
    def _resolve_sweep_seconds() -> int:
        raw_value = os.getenv("AGENT_RUN_SWEEP_SECONDS", "3600").strip()
        try:
            value = int(raw_value)
        except ValueError as error:
            raise ValueError("AGENT_RUN_SWEEP_SECONDS must be a positive integer") from error
        if value <= 0:
            raise ValueError("AGENT_RUN_SWEEP_SECONDS must be a positive integer")
        return value


def _nonempty(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _safe_summary(value: str | None, max_length: int = 1000) -> str | None:
    if value is None:
        return None
    return str(value).replace("\x00", "")[:max_length]


_run_manager: RunManager | None = None


def get_run_manager() -> RunManager:
    """Return the process-wide run manager."""

    global _run_manager
    if _run_manager is None:
        _run_manager = RunManager()
    return _run_manager
