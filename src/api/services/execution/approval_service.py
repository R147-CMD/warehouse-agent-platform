"""Approval lifecycle cryptographically bound to an exact proposed action."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from src.api.domain.agent_protocols import ProposedAction
from src.api.domain.identity import IdentityContext

from .idempotency import action_hash
from .models import ApprovalV2
from .policy import PolicyEngine
from .store import ExecutionStore


class ApprovalService:
    def __init__(
        self,
        store: ExecutionStore,
        *,
        policy: PolicyEngine | None = None,
        ttl: timedelta = timedelta(hours=24),
    ) -> None:
        self.store = store
        self.policy = policy or PolicyEngine()
        self.ttl = ttl

    async def request(
        self,
        action: ProposedAction,
        requester: IdentityContext,
        *,
        run_id: str | None = None,
    ) -> ApprovalV2:
        decision = self.policy.evaluate(action, requester)
        if decision.decision == "deny":
            raise PermissionError(",".join(decision.reasons))
        if decision.decision == "fresh_evidence_required":
            raise ValueError("fresh evidence and expected version are required")
        now = datetime.now(UTC)
        approval = ApprovalV2(
            approval_id=str(uuid4()),
            run_id=run_id,
            tenant_id=requester.tenant_id,
            requester_id=requester.user_id,
            action_id=action.action_id,
            action_hash=action_hash(action),
            status="pending",
            required_approvals=2 if decision.decision == "dual_approval" else 1,
            created_at=now,
            expires_at=now + self.ttl,
        )
        await self.store.put_approval(approval)
        return approval

    async def decide(
        self,
        approval_id: str,
        action: ProposedAction,
        approver: IdentityContext,
        *,
        approve: bool,
    ) -> ApprovalV2:
        approval = await self.store.get_approval(approval_id)
        if approval is None:
            raise LookupError("approval not found")
        now = datetime.now(UTC)
        if approval.status != "pending":
            return approval
        if now >= approval.expires_at:
            expired = approval.model_copy(
                update={"status": "expired", "decided_at": now}
            )
            await self.store.put_approval(expired)
            return expired
        if approval.tenant_id != approver.tenant_id:
            raise PermissionError("cross-tenant approval is forbidden")
        if (
            not set(approver.roles)
            & {
                "admin",
                "manager",
                "supervisor",
                "warehouse_manager",
                "safety_manager",
            }
            and "approval.decide" not in approver.scopes
        ):
            raise PermissionError("approver role or scope is required")
        if approval.requester_id == approver.user_id:
            raise ValueError("requester cannot approve their own action")
        if approval.action_hash != action_hash(action):
            raise ValueError("action hash does not match approval")
        if not approve:
            decided = approval.model_copy(
                update={"status": "rejected", "decided_at": now}
            )
        else:
            approvers = tuple(dict.fromkeys((*approval.approver_ids, approver.user_id)))
            status = (
                "approved"
                if len(approvers) >= approval.required_approvals
                else "pending"
            )
            decided = approval.model_copy(
                update={
                    "status": status,
                    "approver_ids": approvers,
                    "decided_at": now if status == "approved" else None,
                }
            )
        await self.store.put_approval(decided)
        return decided
