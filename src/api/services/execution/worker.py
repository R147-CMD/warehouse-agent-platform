"""Outbox consumer that invokes bound adapters and records verified outcomes."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from src.api.services.evidence_v2.store import EvidenceStore

from .execution_evidence import command_readback_evidence
from .models import Command
from .retry_policy import RetryPolicy
from .store import ExecutionStore


class ExecutionOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    accepted: bool
    verified: bool
    external_reference: str | None = None
    readback: dict[str, Any] = Field(default_factory=dict)


CommandHandler = Callable[[Command], ExecutionOutcome | Awaitable[ExecutionOutcome]]


class CommandWorker:
    def __init__(
        self,
        store: ExecutionStore,
        handlers: dict[str, CommandHandler],
        *,
        evidence_store: EvidenceStore | None = None,
        worker_id: str | None = None,
        lease_seconds: int = 60,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self.store = store
        self.handlers = handlers
        self.evidence_store = evidence_store
        self.worker_id = worker_id or f"worker-{uuid4()}"
        self.lease_seconds = lease_seconds
        self.retry_policy = retry_policy or RetryPolicy()

    async def process_next(self) -> Command | None:
        events = await self.store.pending_outbox()
        if not events:
            return None
        event = events[0]
        updated = await self.process(event.command_id)
        if updated.status != "pending":
            await self.store.mark_delivered(
                event.model_copy(update={"delivered_at": datetime.now(UTC)})
            )
        elif updated.next_attempt_at is not None:
            return None
        return updated

    async def process(self, command_id: str) -> Command:
        command = await self.store.claim_command(
            command_id, self.worker_id, self.lease_seconds
        )
        if command is None:
            current = await self.store.get_command(command_id)
            if current is None:
                raise LookupError("command not found")
            return current
        handler = self.handlers.get(command.capability)
        now = datetime.now(UTC)
        if handler is None:
            updated = command.model_copy(
                update={
                    "status": "failed",
                    "error": "command handler unavailable",
                    "lease_owner": None,
                    "lease_expires_at": None,
                    "updated_at": now,
                }
            )
        else:
            running = command
            heartbeat = asyncio.create_task(self._heartbeat(running.command_id))
            try:
                outcome = handler(running)
                if inspect.isawaitable(outcome):
                    outcome = await outcome
                outcome = ExecutionOutcome.model_validate(outcome)
                status = (
                    "succeeded"
                    if outcome.accepted and outcome.verified
                    else "result_unknown" if outcome.accepted else "failed"
                )
                updated = running.model_copy(
                    update={
                        "status": status,
                        "external_reference": outcome.external_reference,
                        "readback": outcome.readback,
                        "lease_owner": None,
                        "lease_expires_at": None,
                        "updated_at": datetime.now(UTC),
                    }
                )
            except Exception as exc:
                decision = self.retry_policy.classify(exc, attempt=running.attempts)
                status = {
                    "retry": "pending",
                    "reconcile": "result_unknown",
                    "fail": "failed",
                }[decision.disposition]
                next_attempt_at = (
                    datetime.now(UTC) + timedelta(seconds=decision.delay_seconds)
                    if decision.disposition == "retry"
                    else None
                )
                updated = running.model_copy(
                    update={
                        "status": status,
                        "error": (f"{decision.category}: {type(exc).__name__}: {exc}"),
                        "next_attempt_at": next_attempt_at,
                        "lease_owner": None,
                        "lease_expires_at": None,
                        "updated_at": datetime.now(UTC),
                    }
                )
            finally:
                heartbeat.cancel()
                try:
                    await heartbeat
                except asyncio.CancelledError:
                    pass
        if updated.status == "succeeded":
            evidence = command_readback_evidence(updated)
            if self.evidence_store is not None:
                await self.evidence_store.append(evidence)
            updated = updated.model_copy(update={"evidence_refs": (evidence.ref,)})
        await self.store.update_command(updated)
        return updated

    async def _heartbeat(self, command_id: str) -> None:
        interval = max(0.1, self.lease_seconds / 3)
        while True:
            await asyncio.sleep(interval)
            renewed = await self.store.renew_command_lease(
                command_id, self.worker_id, self.lease_seconds
            )
            if not renewed:
                return
