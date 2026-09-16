"""Server-owned action registry and approval-to-command control plane."""

from __future__ import annotations

from datetime import UTC, datetime

from src.api.domain.agent_protocols import ProposedAction
from src.api.domain.identity import IdentityContext

from .approval_service import ApprovalService
from .command_service import CommandService
from .models import ApprovalV2, Command, RegisteredAction
from .store import ExecutionStore, InMemoryExecutionStore


class ControlledExecutionService:
    def __init__(self, store: ExecutionStore | None = None) -> None:
        self.store = store or InMemoryExecutionStore()
        self.approvals = ApprovalService(self.store)
        self.commands = CommandService(self.store)

    async def register(
        self,
        run_id: str,
        requester: IdentityContext,
        actions: tuple[ProposedAction, ...],
    ) -> None:
        for action in actions:
            await self.store.put_registered_action(
                RegisteredAction(
                    run_id=run_id,
                    requester=requester,
                    action=action,
                    created_at=datetime.now(UTC),
                )
            )

    async def request_approval(
        self, action_id: str, requester: IdentityContext
    ) -> ApprovalV2:
        record = await self._get_action(action_id, requester.tenant_id)
        if record.requester.user_id != requester.user_id:
            raise PermissionError("only the action requester can submit it")
        return await self.approvals.request(
            record.action, requester, run_id=record.run_id
        )

    async def decide(
        self,
        approval_id: str,
        approver: IdentityContext,
        *,
        approve: bool,
    ) -> tuple[ApprovalV2, Command | None]:
        approval = await self.store.get_approval(approval_id)
        if approval is None:
            raise LookupError("approval not found")
        record = await self._get_action(approval.action_id, approver.tenant_id)
        decided = await self.approvals.decide(
            approval_id, record.action, approver, approve=approve
        )
        command = None
        if decided.status == "approved":
            command = await self.commands.enqueue(
                decided, record.action, record.requester
            )
        return decided, command

    async def action(self, action_id: str, tenant_id: str) -> ProposedAction:
        return (await self._get_action(action_id, tenant_id)).action

    async def _get_action(self, action_id: str, tenant_id: str) -> RegisteredAction:
        record = await self.store.get_registered_action(action_id, tenant_id)
        if record is None:
            raise LookupError("action not found")
        return record
