from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest

from src.api.domain.agent_protocols import ProposedAction, ResourceRef
from src.api.domain.identity import IdentityContext
from src.api.services.execution.idempotency import action_hash
from src.api.services.execution.models import (
    ApprovalV2,
    Command,
    OutboxEvent,
    RegisteredAction,
)
from src.api.services.execution.postgres_store import PostgresExecutionStore


class Result:
    def __init__(self, rows):
        self.rows = list(rows)

    async def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    async def fetchall(self):
        rows, self.rows = self.rows, []
        return rows


class Connection:
    def __init__(self, responses):
        self.responses = list(responses)
        self.statements = []
        self.transactions = 0

    async def execute(self, statement, parameters=None):
        self.statements.append((str(statement), parameters))
        rows = self.responses.pop(0) if self.responses else []
        return Result(rows)

    @asynccontextmanager
    async def transaction(self):
        self.transactions += 1
        yield self


class Pool:
    def __init__(self, connection):
        self._connection = connection

    @asynccontextmanager
    async def connection(self):
        yield self._connection


def identity() -> IdentityContext:
    return IdentityContext(
        tenant_id="tenant-1",
        user_id="requester",
        roles=("warehouse_manager",),
        scopes=("sap.order.assign",),
        warehouse_scope=("EW01",),
        authenticated_at=datetime(2026, 9, 8, tzinfo=UTC),
    )


def action() -> ProposedAction:
    return ProposedAction(
        action_id="action-1",
        capability="sap.ewm.order.assign",
        target=ResourceRef(
            resource_type="warehouse_order",
            resource_id="2000005003",
            warehouse_id="EW01",
            expected_version='W/"1"',
        ),
        arguments={"warehouse_order": "2000005003", "resource": "RES2"},
        expected_effect="assign order",
        risk_level="high",
        required_scopes=("sap.order.assign",),
        idempotency_key="tenant-1:assign:2000005003:RES2",
    )


@pytest.mark.asyncio
async def test_registered_action_round_trips_through_postgres_contract() -> None:
    created_at = datetime(2026, 9, 8, tzinfo=UTC)
    record = RegisteredAction(
        run_id="run-1", requester=identity(), action=action(), created_at=created_at
    )
    restored_row = {
        "run_id": "run-1",
        "requester_context": identity().model_dump(mode="json"),
        "action_payload": action().model_dump(mode="json"),
        "created_at": created_at,
    }
    connection = Connection([[], [restored_row], [restored_row]])
    store = PostgresExecutionStore(Pool(connection))

    await store.put_registered_action(record)
    restored = await store.get_registered_action("action-1", "tenant-1")

    assert restored == record


@pytest.mark.asyncio
async def test_command_and_outbox_are_created_in_one_transaction() -> None:
    now = datetime(2026, 9, 8, tzinfo=UTC)
    approval = ApprovalV2(
        approval_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        run_id="run-1",
        tenant_id="tenant-1",
        requester_id="requester",
        action_id="action-1",
        action_hash=action_hash(action()),
        status="approved",
        created_at=now,
        expires_at=now + timedelta(hours=1),
        decided_at=now,
    )
    command = Command(
        command_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        run_id="run-1",
        approval_id=approval.approval_id,
        tenant_id="tenant-1",
        capability=action().capability,
        action_id=action().action_id,
        action_hash=approval.action_hash,
        idempotency_key=action().idempotency_key,
        target=action().target.model_dump(mode="json"),
        arguments=action().arguments,
        expected_version=action().target.expected_version,
        created_at=now,
        updated_at=now,
    )
    event = OutboxEvent(
        event_id="cccccccc-cccc-cccc-cccc-cccccccccccc",
        command_id=command.command_id,
        created_at=now,
    )
    approval_row = approval.model_dump(mode="python")
    command_row = command.model_dump(mode="python")
    connection = Connection([[approval_row], [], [command_row], [], []])
    store = PostgresExecutionStore(Pool(connection))

    restored = await store.enqueue_command_once(approval, command, event)

    assert restored == command
    assert connection.transactions == 1
    statements = "\n".join(statement for statement, _ in connection.statements)
    assert "FOR UPDATE" in statements
    assert "INSERT INTO commands_v2" in statements
    assert "INSERT INTO outbox_events_v2" in statements
    assert "UPDATE approvals_v2" in statements


@pytest.mark.asyncio
async def test_outbox_claim_uses_skip_locked_and_a_lease() -> None:
    now = datetime(2026, 9, 8, tzinfo=UTC)
    row = {
        "event_id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
        "command_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        "event_type": "command.requested",
        "created_at": now,
        "claimed_by": "relay-1",
        "lease_expires_at": now + timedelta(seconds=30),
        "delivered_at": None,
    }
    connection = Connection([[row]])
    store = PostgresExecutionStore(Pool(connection))

    events = await store.claim_outbox("relay-1", 10, 30)

    assert events[0].claimed_by == "relay-1"
    statement, parameters = connection.statements[0]
    assert "FOR UPDATE SKIP LOCKED" in statement
    assert parameters == (10, "relay-1", 30)
