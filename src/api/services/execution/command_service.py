"""Create a command and outbox event atomically after approval."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from src.api.domain.agent_protocols import ProposedAction
from src.api.domain.identity import IdentityContext

from .idempotency import action_hash
from .models import ApprovalV2, Command, OutboxEvent
from .store import ExecutionStore


class CommandService:
    def __init__(self, store: ExecutionStore) -> None:
        self.store = store

    async def enqueue(
        self,
        approval: ApprovalV2,
        action: ProposedAction,
        requester: IdentityContext,
    ) -> Command:
        if approval.status != "approved":
            raise PermissionError("an approved action is required")
        if approval.tenant_id != requester.tenant_id:
            raise PermissionError("cross-tenant command is forbidden")
        current_hash = action_hash(action)
        if current_hash != approval.action_hash:
            raise ValueError("approved action hash changed")
        now = datetime.now(UTC)
        command_id = str(uuid4())
        command = Command(
            command_id=command_id,
            run_id=approval.run_id,
            approval_id=approval.approval_id,
            tenant_id=requester.tenant_id,
            capability=action.capability,
            action_id=action.action_id,
            action_hash=current_hash,
            idempotency_key=action.idempotency_key,
            target=action.target.model_dump(mode="json"),
            arguments=action.arguments,
            expected_version=action.target.expected_version,
            created_at=now,
            updated_at=now,
        )
        event = OutboxEvent(
            event_id=str(uuid4()), command_id=command_id, created_at=now
        )
        return await self.store.enqueue_command_once(approval, command, event)
