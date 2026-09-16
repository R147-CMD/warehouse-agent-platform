"""Durable execution-domain contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.api.domain.agent_protocols import ProposedAction
from src.api.domain.evidence_protocols import EvidenceRef
from src.api.domain.identity import IdentityContext


class PolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: Literal[
        "allow", "deny", "approval_required", "dual_approval", "fresh_evidence_required"
    ]
    risk_level: Literal["low", "medium", "high", "critical"]
    reasons: tuple[str, ...]


class ApprovalV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    approval_id: str
    run_id: str | None = None
    tenant_id: str
    requester_id: str
    action_id: str
    action_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["pending", "approved", "rejected", "expired", "consumed"]
    required_approvals: int = Field(default=1, ge=1, le=2)
    approver_ids: tuple[str, ...] = ()
    created_at: datetime
    expires_at: datetime
    decided_at: datetime | None = None


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    command_id: str
    run_id: str | None = None
    approval_id: str | None = None
    tenant_id: str
    capability: str
    action_id: str
    action_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str
    target: dict[str, Any]
    arguments: dict[str, Any]
    expected_version: str | None = None
    status: Literal[
        "pending",
        "running",
        "succeeded",
        "failed",
        "result_unknown",
        "cancelled",
    ] = "pending"
    attempts: int = Field(default=0, ge=0)
    next_attempt_at: datetime | None = None
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    external_reference: str | None = None
    readback: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: tuple[EvidenceRef, ...] = ()
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class OutboxEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    command_id: str
    event_type: str = "command.requested"
    created_at: datetime
    claimed_by: str | None = None
    lease_expires_at: datetime | None = None
    delivered_at: datetime | None = None


class RegisteredAction(BaseModel):
    """Server-owned action payload required to resume approval after restart."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    requester: IdentityContext
    action: ProposedAction
    created_at: datetime
