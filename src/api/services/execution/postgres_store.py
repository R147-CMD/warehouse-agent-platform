"""PostgreSQL execution store for restart-safe approvals and commands."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg.types.json import Jsonb

from src.api.domain.agent_protocols import ProposedAction
from src.api.domain.identity import IdentityContext

from .idempotency import action_hash
from .models import ApprovalV2, Command, OutboxEvent, RegisteredAction


class PostgresExecutionStore:
    """Persist the controlled-execution state using short transactions."""

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def put_registered_action(self, record: RegisteredAction) -> None:
        statement = """
            INSERT INTO proposed_actions_v2 (
                tenant_id, action_id, run_id, requester_id,
                requester_context, action_payload, action_hash, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, action_id) DO NOTHING
        """
        parameters = (
            record.requester.tenant_id,
            record.action.action_id,
            record.run_id,
            record.requester.user_id,
            Jsonb(record.requester.model_dump(mode="json")),
            Jsonb(record.action.model_dump(mode="json")),
            action_hash(record.action),
            record.created_at,
        )
        async with self._pool.connection() as connection:
            await connection.execute(statement, parameters)
            result = await connection.execute(
                """
                SELECT run_id, requester_context, action_payload, created_at
                FROM proposed_actions_v2
                WHERE tenant_id = %s AND action_id = %s
                """,
                (record.requester.tenant_id, record.action.action_id),
            )
            row = await result.fetchone()
        restored = _registered_action_from_row(row) if row is not None else None
        if restored is None or not _same_registration(restored, record):
            raise ValueError("action ID already belongs to another proposal")

    async def get_registered_action(
        self, action_id: str, tenant_id: str
    ) -> RegisteredAction | None:
        async with self._pool.connection() as connection:
            result = await connection.execute(
                """
                SELECT run_id, requester_context, action_payload, created_at
                FROM proposed_actions_v2
                WHERE tenant_id = %s AND action_id = %s
                """,
                (tenant_id, action_id),
            )
            row = await result.fetchone()
        return _registered_action_from_row(row) if row is not None else None

    async def put_approval(self, approval: ApprovalV2) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(
                """
                INSERT INTO approvals_v2 (
                    approval_id, tenant_id, run_id, requester_id, action_id,
                    action_hash, status, required_approvals, approver_ids,
                    created_at, expires_at, decided_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (approval_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    approver_ids = EXCLUDED.approver_ids,
                    decided_at = EXCLUDED.decided_at
                WHERE approvals_v2.tenant_id = EXCLUDED.tenant_id
                  AND approvals_v2.action_hash = EXCLUDED.action_hash
                """,
                (
                    approval.approval_id,
                    approval.tenant_id,
                    approval.run_id,
                    approval.requester_id,
                    approval.action_id,
                    approval.action_hash,
                    approval.status,
                    approval.required_approvals,
                    Jsonb(list(approval.approver_ids)),
                    approval.created_at,
                    approval.expires_at,
                    approval.decided_at,
                ),
            )

    async def get_approval(self, approval_id: str) -> ApprovalV2 | None:
        async with self._pool.connection() as connection:
            result = await connection.execute(
                "SELECT * FROM approvals_v2 WHERE approval_id = %s",
                (approval_id,),
            )
            row = await result.fetchone()
        return _approval_from_row(row) if row is not None else None

    async def enqueue_command_once(
        self, approval: ApprovalV2, command: Command, event: OutboxEvent
    ) -> Command:
        if command.approval_id is None:
            raise ValueError("durable command requires approval_id")
        async with self._pool.connection() as connection:
            async with connection.transaction():
                result = await connection.execute(
                    "SELECT * FROM approvals_v2 WHERE approval_id = %s FOR UPDATE",
                    (approval.approval_id,),
                )
                approval_row = await result.fetchone()
                if approval_row is None:
                    raise LookupError("approval not found")
                persisted_approval = _approval_from_row(approval_row)
                if (
                    persisted_approval.tenant_id != command.tenant_id
                    or persisted_approval.action_hash != command.action_hash
                ):
                    raise PermissionError("approval does not authorize this command")
                if persisted_approval.status not in {"approved", "consumed"}:
                    raise PermissionError("approved action is required")

                result = await connection.execute(
                    """
                    SELECT * FROM commands_v2
                    WHERE tenant_id = %s AND idempotency_key = %s
                    """,
                    (command.tenant_id, command.idempotency_key),
                )
                existing_row = await result.fetchone()
                if existing_row is not None:
                    return _command_from_row(existing_row)

                result = await connection.execute(
                    """
                    INSERT INTO commands_v2 (
                        command_id, tenant_id, run_id, approval_id, capability,
                        action_id, action_hash, idempotency_key, target,
                        arguments, expected_version, status, attempts, next_attempt_at,
                        external_reference, readback, evidence_refs, error,
                        created_at, updated_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    RETURNING *
                    """,
                    _command_parameters(command),
                )
                inserted_row = await result.fetchone()
                if inserted_row is None:
                    raise RuntimeError("command insert did not return a row")

                await connection.execute(
                    """
                    INSERT INTO outbox_events_v2 (
                        event_id, aggregate_type, aggregate_id, event_type,
                        payload, created_at, available_at
                    )
                    VALUES (%s, 'command', %s, %s, %s, %s, %s)
                    """,
                    (
                        event.event_id,
                        event.command_id,
                        event.event_type,
                        Jsonb({"command_id": event.command_id}),
                        event.created_at,
                        event.created_at,
                    ),
                )
                await connection.execute(
                    """
                    UPDATE approvals_v2
                    SET status = 'consumed'
                    WHERE approval_id = %s AND status = 'approved'
                    """,
                    (approval.approval_id,),
                )
                return _command_from_row(inserted_row)

    async def get_command(self, command_id: str) -> Command | None:
        async with self._pool.connection() as connection:
            result = await connection.execute(
                "SELECT * FROM commands_v2 WHERE command_id = %s",
                (command_id,),
            )
            row = await result.fetchone()
        return _command_from_row(row) if row is not None else None

    async def claim_command(
        self, command_id: str, worker_id: str, lease_seconds: int
    ) -> Command | None:
        async with self._pool.connection() as connection:
            result = await connection.execute(
                """
                UPDATE commands_v2
                SET status = 'running',
                    attempts = attempts + 1,
                    lease_owner = %s,
                    lease_expires_at = NOW() + (%s * INTERVAL '1 second'),
                    updated_at = NOW()
                WHERE command_id = %s
                  AND (
                    (
                        status = 'pending'
                        AND (next_attempt_at IS NULL OR next_attempt_at <= NOW())
                    )
                    OR (
                        status = 'running'
                        AND (lease_expires_at IS NULL OR lease_expires_at <= NOW())
                    )
                  )
                RETURNING *
                """,
                (worker_id, lease_seconds, command_id),
            )
            row = await result.fetchone()
        return _command_from_row(row) if row is not None else None

    async def renew_command_lease(
        self, command_id: str, worker_id: str, lease_seconds: int
    ) -> bool:
        async with self._pool.connection() as connection:
            result = await connection.execute(
                """
                UPDATE commands_v2
                SET lease_expires_at = NOW() + (%s * INTERVAL '1 second'),
                    updated_at = NOW()
                WHERE command_id = %s
                  AND status = 'running'
                  AND lease_owner = %s
                RETURNING command_id
                """,
                (lease_seconds, command_id, worker_id),
            )
            row = await result.fetchone()
        return row is not None

    async def pending_outbox(self) -> tuple[OutboxEvent, ...]:
        async with self._pool.connection() as connection:
            result = await connection.execute("""
                SELECT event_id, aggregate_id AS command_id, event_type,
                       created_at, claimed_by, lease_expires_at, delivered_at
                FROM outbox_events_v2
                WHERE delivered_at IS NULL AND available_at <= NOW()
                ORDER BY created_at, event_id
                LIMIT 100
                """)
            rows = await result.fetchall()
        return tuple(OutboxEvent.model_validate(row) for row in rows)

    async def claim_outbox(
        self, relay_id: str, limit: int, lease_seconds: int
    ) -> tuple[OutboxEvent, ...]:
        async with self._pool.connection() as connection:
            result = await connection.execute(
                """
                WITH candidates AS (
                    SELECT event_id
                    FROM outbox_events_v2
                    WHERE delivered_at IS NULL
                      AND available_at <= NOW()
                      AND (
                          claimed_by IS NULL
                          OR lease_expires_at IS NULL
                          OR lease_expires_at <= NOW()
                      )
                    ORDER BY created_at, event_id
                    FOR UPDATE SKIP LOCKED
                    LIMIT %s
                )
                UPDATE outbox_events_v2 AS event
                SET claimed_by = %s,
                    lease_expires_at = NOW() + (%s * INTERVAL '1 second')
                FROM candidates
                WHERE event.event_id = candidates.event_id
                RETURNING event.event_id,
                          event.aggregate_id AS command_id,
                          event.event_type,
                          event.created_at,
                          event.claimed_by,
                          event.lease_expires_at,
                          event.delivered_at
                """,
                (limit, relay_id, lease_seconds),
            )
            rows = await result.fetchall()
        return tuple(OutboxEvent.model_validate(row) for row in rows)

    async def release_outbox(self, event_id: str, relay_id: str) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(
                """
                UPDATE outbox_events_v2
                SET claimed_by = NULL, lease_expires_at = NULL
                WHERE event_id = %s
                  AND claimed_by = %s
                  AND delivered_at IS NULL
                """,
                (event_id, relay_id),
            )

    async def update_command(self, command: Command) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(
                """
                UPDATE commands_v2 SET
                    status = %s, attempts = %s, external_reference = %s,
                    readback = %s, evidence_refs = %s, error = %s, updated_at = %s,
                    next_attempt_at = %s, lease_owner = %s, lease_expires_at = %s
                WHERE command_id = %s AND tenant_id = %s
                """,
                (
                    command.status,
                    command.attempts,
                    command.external_reference,
                    Jsonb(command.readback),
                    Jsonb(
                        [item.model_dump(mode="json") for item in command.evidence_refs]
                    ),
                    Jsonb({"message": command.error}) if command.error else None,
                    command.updated_at,
                    command.next_attempt_at,
                    command.lease_owner,
                    command.lease_expires_at,
                    command.command_id,
                    command.tenant_id,
                ),
            )

    async def mark_delivered(self, event: OutboxEvent) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(
                """
                UPDATE outbox_events_v2
                SET delivered_at = %s, claimed_by = NULL, lease_expires_at = NULL
                WHERE event_id = %s AND delivered_at IS NULL
                """,
                (event.delivered_at, event.event_id),
            )


def _same_registration(left: RegisteredAction, right: RegisteredAction) -> bool:
    return (
        left.run_id == right.run_id
        and left.requester == right.requester
        and left.action == right.action
    )


def _registered_action_from_row(row: dict[str, Any]) -> RegisteredAction:
    return RegisteredAction(
        run_id=str(row["run_id"]),
        requester=IdentityContext.model_validate(row["requester_context"]),
        action=ProposedAction.model_validate(row["action_payload"]),
        created_at=row["created_at"],
    )


def _approval_from_row(row: dict[str, Any]) -> ApprovalV2:
    values = dict(row)
    values["approval_id"] = str(values["approval_id"])
    if values.get("run_id") is not None:
        values["run_id"] = str(values["run_id"])
    values["approver_ids"] = tuple(values.get("approver_ids") or ())
    return ApprovalV2.model_validate(values)


def _command_parameters(command: Command) -> tuple[Any, ...]:
    return (
        command.command_id,
        command.tenant_id,
        command.run_id,
        command.approval_id,
        command.capability,
        command.action_id,
        command.action_hash,
        command.idempotency_key,
        Jsonb(command.target),
        Jsonb(command.arguments),
        command.expected_version,
        command.status,
        command.attempts,
        command.next_attempt_at,
        command.external_reference,
        Jsonb(command.readback),
        Jsonb([item.model_dump(mode="json") for item in command.evidence_refs]),
        Jsonb({"message": command.error}) if command.error else None,
        command.created_at,
        command.updated_at,
    )


def _command_from_row(row: dict[str, Any]) -> Command:
    values = dict(row)
    for key in ("command_id", "run_id", "approval_id"):
        if values.get(key) is not None:
            values[key] = str(values[key])
    raw_error = values.get("error")
    if isinstance(raw_error, dict):
        values["error"] = raw_error.get("message")
    values["readback"] = values.get("readback") or {}
    values["evidence_refs"] = tuple(values.get("evidence_refs") or ())
    allowed = set(Command.model_fields)
    return Command.model_validate(
        {key: value for key, value in values.items() if key in allowed}
    )
