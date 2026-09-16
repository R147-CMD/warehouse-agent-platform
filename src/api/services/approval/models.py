"""Domain models for durable human approval of tool execution."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


APPROVAL_TTL = timedelta(hours=24)


class ApprovalStatus(str, Enum):
    """Lifecycle states for an approval record."""

    PENDING = "pending"
    APPROVED = "approved"
    EXECUTING = "executing"
    EXECUTED = "executed"
    REJECTED = "rejected"
    EXPIRED = "expired"
    FAILED = "failed"


class ApprovalDecision(str, Enum):
    """A decision an authorized approver can make."""

    APPROVE = "approve"
    REJECT = "reject"


@dataclass(frozen=True)
class ApprovalExecutionContext:
    """Server-authenticated identity and checkpoint information for a graph run."""

    thread_id: str
    checkpoint_ns: str
    request_id: str
    requester_id: int
    requester_username: str
    run_id: UUID | None = None


class ApprovalInterruptPayload(BaseModel):
    """Safe, UI-facing data emitted through a LangGraph interrupt."""

    approval_id: UUID
    run_id: UUID | None = None
    action: str
    tool_name: str
    arguments: dict[str, Any]
    risk_level: Literal["high", "unknown"]
    risk_reasons: list[str]
    requester_username: str
    created_at: datetime
    expires_at: datetime


class ApprovalResumePayload(BaseModel):
    """Decision data supplied when resuming an interrupted graph."""

    approval_id: UUID
    decision: ApprovalDecision
    approver_id: int | None
    approver_username: str
    reason: str | None = Field(default=None, max_length=500)


class ApprovalRecord(BaseModel):
    """Persistent approval state used for auditability and replay-safe execution."""

    approval_id: UUID
    thread_id: str
    checkpoint_ns: str
    request_id: str
    action_key: str
    idempotency_key: str
    tool_key: str
    tool_name: str
    arguments: dict[str, Any]
    risk_level: Literal["high", "unknown"]
    risk_reasons: list[str]
    requester_id: int
    requester_username: str
    run_id: UUID | None = None
    approver_id: int | None = None
    approver_username: str | None = None
    decision_reason: str | None = None
    status: ApprovalStatus
    result: Any | None = None
    error: str | None = None
    created_at: datetime
    expires_at: datetime
    decided_at: datetime | None = None
    execution_started_at: datetime | None = None
    executed_at: datetime | None = None
    updated_at: datetime

    def to_interrupt_payload(self) -> ApprovalInterruptPayload:
        """Return only the fields that are safe to expose to an approver UI."""

        return ApprovalInterruptPayload(
            approval_id=self.approval_id,
            run_id=self.run_id,
            action=self.action_key,
            tool_name=self.tool_name,
            arguments=self.arguments,
            risk_level=self.risk_level,
            risk_reasons=self.risk_reasons,
            requester_username=self.requester_username,
            created_at=self.created_at,
            expires_at=self.expires_at,
        )


@dataclass(frozen=True)
class RiskAssessment:
    """Fail-closed classification result for a discovered tool."""

    requires_approval: bool
    risk_level: Literal["read", "high", "unknown"]
    reasons: tuple[str, ...]


class ApprovalRejectedError(RuntimeError):
    """Raised before a denied or expired tool action can execute."""

    def __init__(self, message: str = "Approval was not granted; the action was not executed."):
        super().__init__(message)


class ApprovalConflictError(RuntimeError):
    """Raised when an approval transition would produce an unsafe conflict."""

    def __init__(self, message: str = "Approval state conflict; refresh the approval and try again."):
        super().__init__(message)
