"""Celery/Redis transport for execution commands.

The API process only relays committed outbox records.  SAP writes run in a
separate Celery worker and still use the durable command lease/idempotency
boundary, so Celery's at-least-once delivery cannot create a second command.
"""

from __future__ import annotations

import asyncio
import os
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from celery import Celery

from .models import Command

EXECUTE_TASK_NAME = "warehouse.execution.execute_command"
RECONCILE_TASK_NAME = "warehouse.execution.reconcile_command"


def create_celery_app() -> Celery:
    broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
    result_backend = os.getenv("CELERY_RESULT_BACKEND") or None
    app = Celery("warehouse_execution", broker=broker_url, backend=result_backend)
    app.conf.update(
        task_serializer="json",
        accept_content=("json",),
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        broker_connection_retry_on_startup=True,
        task_default_queue=os.getenv(
            "WAREHOUSE_EXECUTION_CELERY_QUEUE", "warehouse.commands"
        ),
    )
    return app


celery_app = create_celery_app()


class CeleryCommandPublisher:
    """Translate an outbox event into an idempotently identifiable Celery task."""

    def __init__(self, app: Any = celery_app, *, queue: str | None = None) -> None:
        self.app = app
        self.queue = queue or os.getenv(
            "WAREHOUSE_EXECUTION_CELERY_QUEUE", "warehouse.commands"
        )

    def __call__(self, event_id: str, command_id: str) -> None:
        self.app.send_task(
            EXECUTE_TASK_NAME,
            args=[command_id],
            task_id=event_id,
            queue=self.queue,
            headers={"outbox_event_id": event_id},
        )


class _AsyncLoopRunner:
    """Keep async database/HTTP clients on one event loop in a Celery process."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="warehouse-execution-async-loop",
            daemon=True,
        )
        self._thread.start()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def run(self, coroutine):
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop).result()


@dataclass
class _ExecutionRuntime:
    worker: Any
    reconciler: Any


_loop_runner: _AsyncLoopRunner | None = None
_execution_runtime: _ExecutionRuntime | None = None


def _runner() -> _AsyncLoopRunner:
    global _loop_runner
    if _loop_runner is None:
        _loop_runner = _AsyncLoopRunner()
    return _loop_runner


async def _get_runtime() -> _ExecutionRuntime:
    global _execution_runtime
    if _execution_runtime is not None:
        return _execution_runtime

    from src.api.services.mcp.adapters.sap_ewm_adapter import (
        get_sap_ewm_mcp_adapter,
    )

    from .manager import get_execution_store_manager
    from .reconciler import CommandReconciler
    from .sap_handlers import SAPEWMCommandHandlers
    from .worker import CommandWorker

    manager = get_execution_store_manager()
    await manager.start()
    sap_adapter = await get_sap_ewm_mcp_adapter()
    if sap_adapter is None:
        raise RuntimeError("SAP EWM provider is disabled in the Celery worker")
    handlers = SAPEWMCommandHandlers(
        sap_adapter.wms_service,
        connection_id=sap_adapter.sap_config.connection_id,
    )
    _execution_runtime = _ExecutionRuntime(
        worker=CommandWorker(manager.store, handlers.bindings()),
        reconciler=CommandReconciler(manager.store, handlers.readback_bindings()),
    )
    return _execution_runtime


async def _execute(command_id: str) -> Command:
    runtime = await _get_runtime()
    return await runtime.worker.process(command_id)


async def _reconcile(command_id: str) -> Command:
    runtime = await _get_runtime()
    return await runtime.reconciler.reconcile(command_id)


@celery_app.task(bind=True, name=EXECUTE_TASK_NAME, max_retries=10)
def execute_command_task(task, command_id: str) -> dict[str, Any]:
    command = _runner().run(_execute(command_id))
    if command.status == "pending":
        delay = _seconds_until(command.next_attempt_at)
        raise task.retry(
            exc=RuntimeError("command scheduled for classified retry"),
            countdown=delay,
        )
    if command.status == "result_unknown":
        celery_app.send_task(
            RECONCILE_TASK_NAME,
            args=[command.command_id],
            queue=os.getenv("WAREHOUSE_EXECUTION_CELERY_QUEUE", "warehouse.commands"),
            countdown=int(
                os.getenv("WAREHOUSE_EXECUTION_RECONCILE_DELAY_SECONDS", "5")
            ),
        )
    return _task_result(command)


@celery_app.task(bind=True, name=RECONCILE_TASK_NAME, max_retries=5)
def reconcile_command_task(task, command_id: str) -> dict[str, Any]:
    command = _runner().run(_reconcile(command_id))
    if command.status == "result_unknown":
        raise task.retry(
            exc=RuntimeError("external outcome is still unknown"),
            countdown=int(
                os.getenv("WAREHOUSE_EXECUTION_RECONCILE_DELAY_SECONDS", "5")
            ),
        )
    return _task_result(command)


def _seconds_until(moment: datetime | None) -> int:
    if moment is None:
        return 1
    return max(1, int((moment - datetime.now(UTC)).total_seconds()))


def _task_result(command: Command) -> dict[str, Any]:
    return {
        "command_id": command.command_id,
        "status": command.status,
        "attempts": command.attempts,
    }
