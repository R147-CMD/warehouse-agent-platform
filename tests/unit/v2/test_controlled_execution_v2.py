from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from src.adapters.wms.sap_ewm_errors import SAPEWMError, SAPEWMErrorCode
from src.api.domain.agent_protocols import ProposedAction, ResourceRef
from src.api.domain.identity import IdentityContext
from src.api.services.execution.approval_service import ApprovalService
from src.api.services.execution.command_service import CommandService
from src.api.services.execution.control_plane import ControlledExecutionService
from src.api.services.execution.policy import PolicyEngine
from src.api.services.execution.reconciler import CommandReconciler
from src.api.services.execution.store import InMemoryExecutionStore
from src.api.services.execution.worker import CommandWorker, ExecutionOutcome


def identity(user="requester", scopes=("sap.order.assign",)):
    return IdentityContext(
        tenant_id="t1",
        user_id=user,
        roles=("warehouse_manager",),
        scopes=scopes,
        warehouse_scope=("WH-01",),
        authenticated_at=datetime.now(UTC),
    )


def action(resource="WO-1"):
    return ProposedAction(
        action_id="act-1",
        capability="sap.ewm.order.assign",
        target=ResourceRef(
            resource_type="warehouse_order",
            resource_id=resource,
            warehouse_id="WH-01",
            expected_version='W/"7"',
        ),
        arguments={"warehouse_order": resource, "resource": "USER-2"},
        expected_effect="assign warehouse order",
        risk_level="high",
        required_scopes=("sap.order.assign",),
        idempotency_key="t1:sap.ewm.order.assign:WO-1:USER-2",
    )


def test_policy_is_scope_and_warehouse_constrained() -> None:
    assert PolicyEngine().evaluate(action(), identity()).decision == "approval_required"
    assert PolicyEngine().evaluate(action(), identity(scopes=())).decision == "deny"
    outside = action().model_copy(
        update={"target": action().target.model_copy(update={"warehouse_id": "WH-99"})}
    )
    assert PolicyEngine().evaluate(outside, identity()).decision == "deny"


@pytest.mark.asyncio
async def test_approval_binds_exact_action_hash_and_separates_duties() -> None:
    store = InMemoryExecutionStore()
    service = ApprovalService(store)
    pending = await service.request(action(), identity())

    with pytest.raises(ValueError, match="cannot approve their own"):
        await service.decide(pending.approval_id, action(), identity(), approve=True)

    approver = identity(user="approver")
    changed = action("WO-2")
    with pytest.raises(ValueError, match="action hash"):
        await service.decide(pending.approval_id, changed, approver, approve=True)

    approved = await service.decide(
        pending.approval_id, action(), approver, approve=True
    )
    assert approved.status == "approved"


@pytest.mark.asyncio
async def test_approved_action_enqueues_once_and_worker_verifies_readback() -> None:
    store = InMemoryExecutionStore()
    approval_service = ApprovalService(store)
    pending = await approval_service.request(action(), identity())
    approved = await approval_service.decide(
        pending.approval_id, action(), identity(user="approver"), approve=True
    )
    command_service = CommandService(store)

    first = await command_service.enqueue(approved, action(), identity())
    second = await command_service.enqueue(approved, action(), identity())
    assert first.command_id == second.command_id
    assert len(await store.pending_outbox()) == 1

    calls = []

    async def execute(command):
        calls.append(command.command_id)
        return ExecutionOutcome(
            accepted=True,
            verified=True,
            external_reference="sap:WO-1",
            readback={"warehouse_order": "WO-1", "resource": "USER-2"},
        )

    worker = CommandWorker(store, {"sap.ewm.order.assign": execute})
    result = await worker.process_next()

    assert result.status == "succeeded"
    assert result.readback["resource"] == "USER-2"
    assert len(result.evidence_refs) == 1
    assert result.evidence_refs[0].evidence_type == "execution_readback"
    assert calls == [first.command_id]
    assert await worker.process_next() is None


@pytest.mark.asyncio
async def test_control_plane_recovers_registered_action_from_shared_store() -> None:
    """A process restart must not lose the action that an approval refers to."""

    store = InMemoryExecutionStore()
    first_process = ControlledExecutionService(store)
    await first_process.register("run-1", identity(), (action(),))

    restarted_process = ControlledExecutionService(store)
    pending = await restarted_process.request_approval("act-1", identity())
    approval, command = await restarted_process.decide(
        pending.approval_id,
        identity("approver"),
        approve=True,
    )

    assert approval.status == "approved"
    assert command is not None
    assert command.action_id == "act-1"
    assert command.run_id == "run-1"
    assert command.approval_id == approval.approval_id


@pytest.mark.asyncio
async def test_command_claim_prevents_concurrent_duplicate_side_effects() -> None:
    store = InMemoryExecutionStore()
    service = ApprovalService(store)
    pending = await service.request(action(), identity())
    approved = await service.decide(
        pending.approval_id, action(), identity("approver"), approve=True
    )
    command = await CommandService(store).enqueue(approved, action(), identity())
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def execute_once(_command):
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        return ExecutionOutcome(accepted=True, verified=True)

    first = CommandWorker(
        store, {"sap.ewm.order.assign": execute_once}, worker_id="worker-1"
    )
    second = CommandWorker(
        store, {"sap.ewm.order.assign": execute_once}, worker_id="worker-2"
    )

    first_task = asyncio.create_task(first.process(command.command_id))
    await entered.wait()
    second_result = await second.process(command.command_id)
    release.set()
    first_result = await first_task

    assert calls == 1
    assert first_result.status == "succeeded"
    assert second_result.status == "running"


@pytest.mark.asyncio
async def test_transient_failure_is_scheduled_but_not_immediately_retried() -> None:
    store = InMemoryExecutionStore()
    pending = await ApprovalService(store).request(action(), identity())
    approved = await ApprovalService(store).decide(
        pending.approval_id, action(), identity("approver"), approve=True
    )
    command = await CommandService(store).enqueue(approved, action(), identity())
    calls = 0

    async def unavailable(_command):
        nonlocal calls
        calls += 1
        raise SAPEWMError(
            SAPEWMErrorCode.SAP_UNAVAILABLE,
            "temporary outage",
            status_code=503,
            retriable=True,
        )

    worker = CommandWorker(store, {action().capability: unavailable})
    result = await worker.process(command.command_id)
    immediate = await worker.process(command.command_id)

    assert result.status == "pending"
    assert result.next_attempt_at is not None
    assert immediate.status == "pending"
    assert calls == 1


@pytest.mark.asyncio
async def test_unknown_result_is_read_back_before_any_second_write() -> None:
    store = InMemoryExecutionStore()
    pending = await ApprovalService(store).request(action(), identity())
    approved = await ApprovalService(store).decide(
        pending.approval_id, action(), identity("approver"), approve=True
    )
    command = await CommandService(store).enqueue(approved, action(), identity())
    write_calls = 0

    async def response_lost(_command):
        nonlocal write_calls
        write_calls += 1
        raise SAPEWMError.unknown_outcome("write response lost")

    worker = CommandWorker(store, {action().capability: response_lost})
    unknown = await worker.process(command.command_id)
    reconciler = CommandReconciler(
        store,
        {
            action().capability: lambda _command: ExecutionOutcome(
                accepted=True,
                verified=True,
                external_reference="sap:WO-1",
                readback={"warehouse_order": "WO-1", "resource": "USER-2"},
            )
        },
    )
    verified = await reconciler.reconcile(command.command_id)

    assert unknown.status == "result_unknown"
    assert verified.status == "succeeded"
    assert len(verified.evidence_refs) == 1
    assert verified.evidence_refs[0].evidence_type == "execution_readback"
    assert write_calls == 1


@pytest.mark.asyncio
async def test_worker_heartbeat_prevents_lease_theft_during_a_slow_call() -> None:
    store = InMemoryExecutionStore()
    pending = await ApprovalService(store).request(action(), identity())
    approved = await ApprovalService(store).decide(
        pending.approval_id, action(), identity("approver"), approve=True
    )
    command = await CommandService(store).enqueue(approved, action(), identity())
    entered = asyncio.Event()
    release = asyncio.Event()

    async def slow_call(_command):
        entered.set()
        await release.wait()
        return ExecutionOutcome(accepted=True, verified=True)

    first = CommandWorker(
        store,
        {action().capability: slow_call},
        worker_id="worker-1",
        lease_seconds=1,
    )
    second = CommandWorker(
        store,
        {action().capability: slow_call},
        worker_id="worker-2",
        lease_seconds=1,
    )
    first_task = asyncio.create_task(first.process(command.command_id))
    await entered.wait()
    await asyncio.sleep(1.1)

    competing_result = await second.process(command.command_id)
    release.set()
    first_result = await first_task

    assert competing_result.status == "running"
    assert competing_result.lease_owner == "worker-1"
    assert first_result.status == "succeeded"
