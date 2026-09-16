"""Execution repository contract with a concurrency-safe in-memory implementation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from .models import ApprovalV2, Command, OutboxEvent, RegisteredAction


class ExecutionStore(Protocol):
    async def put_registered_action(self, record: RegisteredAction) -> None: ...

    async def get_registered_action(
        self, action_id: str, tenant_id: str
    ) -> RegisteredAction | None: ...

    async def put_approval(self, approval: ApprovalV2) -> None: ...

    async def get_approval(self, approval_id: str) -> ApprovalV2 | None: ...

    async def enqueue_command_once(
        self, approval: ApprovalV2, command: Command, event: OutboxEvent
    ) -> Command: ...

    async def get_command(self, command_id: str) -> Command | None: ...

    async def claim_command(
        self, command_id: str, worker_id: str, lease_seconds: int
    ) -> Command | None: ...

    async def renew_command_lease(
        self, command_id: str, worker_id: str, lease_seconds: int
    ) -> bool: ...

    async def pending_outbox(self) -> tuple[OutboxEvent, ...]: ...

    async def claim_outbox(
        self, relay_id: str, limit: int, lease_seconds: int
    ) -> tuple[OutboxEvent, ...]: ...

    async def release_outbox(self, event_id: str, relay_id: str) -> None: ...

    async def update_command(self, command: Command) -> None: ...

    async def mark_delivered(self, event: OutboxEvent) -> None: ...


@dataclass
class InMemoryExecutionStore:
    def __init__(self) -> None:
        self.actions: dict[tuple[str, str], RegisteredAction] = {}
        self.approvals: dict[str, ApprovalV2] = {}
        self.commands: dict[str, Command] = {}
        self.commands_by_idempotency: dict[str, str] = {}
        self.outbox: dict[str, OutboxEvent] = {}
        self._lock = asyncio.Lock()

    async def put_registered_action(self, record: RegisteredAction) -> None:
        key = (record.requester.tenant_id, record.action.action_id)
        async with self._lock:
            existing = self.actions.get(key)
            if existing is not None and existing != record:
                raise ValueError("action ID already belongs to another proposal")
            self.actions[key] = record

    async def get_registered_action(
        self, action_id: str, tenant_id: str
    ) -> RegisteredAction | None:
        return self.actions.get((tenant_id, action_id))

    async def put_approval(self, approval: ApprovalV2) -> None:
        async with self._lock:
            self.approvals[approval.approval_id] = approval

    async def get_approval(self, approval_id: str) -> ApprovalV2 | None:
        return self.approvals.get(approval_id)

    async def enqueue_command_once(
        self, approval: ApprovalV2, command: Command, event: OutboxEvent
    ) -> Command:
        async with self._lock:
            existing_id = self.commands_by_idempotency.get(command.idempotency_key)
            if existing_id:
                return self.commands[existing_id]
            self.commands[command.command_id] = command
            self.commands_by_idempotency[command.idempotency_key] = command.command_id
            self.outbox[event.event_id] = event
            self.approvals[approval.approval_id] = approval.model_copy(
                update={"status": "consumed"}
            )
            return command

    async def get_command(self, command_id: str) -> Command | None:
        return self.commands.get(command_id)

    async def claim_command(
        self, command_id: str, worker_id: str, lease_seconds: int
    ) -> Command | None:
        now = datetime.now(UTC)
        async with self._lock:
            command = self.commands.get(command_id)
            if command is None or command.status in {
                "succeeded",
                "failed",
                "cancelled",
                "result_unknown",
            }:
                return None
            if (
                command.status == "running"
                and command.lease_expires_at is not None
                and command.lease_expires_at > now
            ):
                return None
            if command.next_attempt_at is not None and command.next_attempt_at > now:
                return None
            claimed = command.model_copy(
                update={
                    "status": "running",
                    "attempts": command.attempts + 1,
                    "lease_owner": worker_id,
                    "lease_expires_at": now + timedelta(seconds=lease_seconds),
                    "updated_at": now,
                }
            )
            self.commands[command_id] = claimed
            return claimed

    async def renew_command_lease(
        self, command_id: str, worker_id: str, lease_seconds: int
    ) -> bool:
        now = datetime.now(UTC)
        async with self._lock:
            command = self.commands.get(command_id)
            if (
                command is None
                or command.status != "running"
                or command.lease_owner != worker_id
            ):
                return False
            self.commands[command_id] = command.model_copy(
                update={
                    "lease_expires_at": now + timedelta(seconds=lease_seconds),
                    "updated_at": now,
                }
            )
            return True

    async def pending_outbox(self) -> tuple[OutboxEvent, ...]:
        return tuple(
            sorted(
                (event for event in self.outbox.values() if event.delivered_at is None),
                key=lambda event: (event.created_at, event.event_id),
            )
        )

    async def claim_outbox(
        self, relay_id: str, limit: int, lease_seconds: int
    ) -> tuple[OutboxEvent, ...]:
        now = datetime.now(UTC)
        claimed: list[OutboxEvent] = []
        async with self._lock:
            candidates = sorted(
                (
                    event
                    for event in self.outbox.values()
                    if event.delivered_at is None
                    and (
                        event.claimed_by is None
                        or event.lease_expires_at is None
                        or event.lease_expires_at <= now
                    )
                ),
                key=lambda event: (event.created_at, event.event_id),
            )
            for event in candidates[:limit]:
                item = event.model_copy(
                    update={
                        "claimed_by": relay_id,
                        "lease_expires_at": now + timedelta(seconds=lease_seconds),
                    }
                )
                self.outbox[item.event_id] = item
                claimed.append(item)
        return tuple(claimed)

    async def release_outbox(self, event_id: str, relay_id: str) -> None:
        async with self._lock:
            event = self.outbox.get(event_id)
            if event is None or event.claimed_by != relay_id:
                return
            self.outbox[event_id] = event.model_copy(
                update={"claimed_by": None, "lease_expires_at": None}
            )

    async def update_command(self, command: Command) -> None:
        async with self._lock:
            self.commands[command.command_id] = command

    async def mark_delivered(self, event: OutboxEvent) -> None:
        async with self._lock:
            self.outbox[event.event_id] = event.model_copy(
                update={"claimed_by": None, "lease_expires_at": None}
            )
