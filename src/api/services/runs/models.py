"""Domain models for durable agent run tracking."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


RUN_RETENTION = timedelta(days=30)


class RunStatus(str, Enum):
    """Lifecycle states for an agent run."""

    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"


class RunType(str, Enum):
    """High-level category for a run ledger row."""

    CHAT = "chat"
    AGENT = "agent"
    TOOL = "tool"
    RETRY = "retry"


class RunEventSeverity(str, Enum):
    """Severity for timeline events."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class RunEventType(str, Enum):
    """Stable event names for the run timeline."""

    RUN_CREATED = "run.created"
    RUN_STARTED = "run.started"
    PLAN_CREATED = "plan.created"
    ROUTE_SELECTED = "route.selected"
    MULTI_AGENT_SELECTED = "multi_agent.selected"
    EVIDENCE_JOINED = "evidence.joined"
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    REFLECTION_REVIEWED = "reflection.reviewed"
    REFLECTION_REPLAN = "reflection.replan"
    REFLECTION_CLARIFICATION_REQUESTED = "reflection.clarification_requested"
    TOOL_STARTED = "tool.started"
    TOOL_COMPLETED = "tool.completed"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_APPROVED = "approval.approved"
    APPROVAL_REJECTED = "approval.rejected"
    APPROVAL_EXPIRED = "approval.expired"
    CHECKPOINT_SAVED = "checkpoint.saved"
    RUN_WAITING_APPROVAL = "run.waiting_approval"
    RUN_CANCEL_REQUESTED = "run.cancel_requested"
    RUN_CANCELLED = "run.cancelled"
    RUN_RETRY_REQUESTED = "run.retry_requested"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"


TERMINAL_STATUSES = {
    RunStatus.COMPLETED,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
}


class RunCancelled(RuntimeError):
    """Raised when a cooperative run cancellation is observed."""

    def __init__(self, run_id: UUID):
        super().__init__(f"Run {run_id} was cancelled")
        self.run_id = run_id


@dataclass(frozen=True)
class RunExecutionContext:
    """Authenticated identity and checkpoint metadata for a run."""

    run_id: UUID
    session_id: str
    checkpoint_thread_id: str
    request_id: str
    user_id: int
    username: str
    user_role: str


class RunRecord(BaseModel):
    """Persistent run ledger row."""

    run_id: UUID
    session_id: str | None = None
    checkpoint_thread_id: str | None = None
    user_id: int
    username: str
    user_role: str
    run_type: RunType
    title: str
    input_summary: str | None = None
    input_payload: dict[str, Any] = Field(default_factory=dict)
    status: RunStatus
    current_agent: str | None = None
    current_tool: str | None = None
    risk_level: str | None = None
    approval_count: int = 0
    error_code: str | None = None
    error_message: str | None = None
    result_summary: str | None = None
    retry_of_run_id: UUID | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime
    expires_at: datetime


class RunEventRecord(BaseModel):
    """Append-only timeline event for a run."""

    event_id: UUID
    run_id: UUID
    event_type: RunEventType
    severity: RunEventSeverity
    agent_name: str | None = None
    tool_name: str | None = None
    approval_id: UUID | None = None
    checkpoint_id: str | None = None
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class RunCreate(BaseModel):
    """Input for creating a run ledger row."""

    session_id: str | None = None
    checkpoint_thread_id: str | None = None
    user_id: int
    username: str
    user_role: str
    run_type: RunType = RunType.CHAT
    title: str
    input_summary: str | None = None
    input_payload: dict[str, Any] = Field(default_factory=dict)
    retry_of_run_id: UUID | None = None


class RunUpdate(BaseModel):
    """Partial update for mutable run state."""

    status: RunStatus | None = None
    current_agent: str | None = None
    current_tool: str | None = None
    risk_level: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    result_summary: str | None = None


class RunListFilters(BaseModel):
    """Filters accepted by the run list API."""

    status: RunStatus | None = None
    run_type: RunType | None = None
    user_id: int | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class RunCancelRequest(BaseModel):
    """Cancel request body."""

    reason: str | None = Field(default=None, max_length=500)


class RunRetryRequest(BaseModel):
    """Retry request body."""

    reason: str | None = Field(default=None, max_length=500)


class RunEventResponse(RunEventRecord):
    """API timeline event response."""


class RunDetailResponse(RunRecord):
    """Run detail with embedded timeline."""

    events: list[RunEventResponse] = Field(default_factory=list)


class RunListResponse(BaseModel):
    """Paginated run list response."""

    items: list[RunRecord]
    total: int
    page: int
    page_size: int
