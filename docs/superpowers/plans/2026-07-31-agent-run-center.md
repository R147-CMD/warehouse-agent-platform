# Agent Run Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a unified Agent Run Center that records agent execution runs, event timelines, approval links, cancellation requests, retry attempts, and a Chinese operations UI.

**Architecture:** Add a focused `src/api/services/runs` domain beside the existing approval service, with PostgreSQL-backed `agent_runs` and `agent_run_events` tables. Instrument the existing FastAPI chat router, LangGraph planner, approval gateway, and React UI without replacing the approval or checkpoint systems.

**Tech Stack:** FastAPI, Pydantic, psycopg async pool, PostgreSQL JSONB, LangGraph, React 19, TypeScript, Material UI, React Query, Axios.

## Global Constraints

- Feature code only in this phase.
- Do not run backend tests, frontend tests, builds, local app restarts, browser validation, or database migration execution.
- Keep query-only actions automatic.
- Require approval for write and high-risk actions.
- Only `manager` and `admin` can approve high-risk actions.
- Each high-risk operation is approved independently.
- `admin` and `manager` can view all runs; other roles can view their own runs.
- Run retention defaults to 30 days.
- Current Git top-level is `E:\`, not this project root, so do not commit changes from this workspace.

---

## File Structure

Create:

- `src/api/services/runs/models.py`: run statuses, event types, typed domain records, API request/response models, and `RunCancelled`.
- `src/api/services/runs/context.py`: context variables for the active run.
- `src/api/services/runs/repository.py`: PostgreSQL setup, CRUD, event append, filtering, cancellation, retry row creation, and retention cleanup.
- `src/api/services/runs/manager.py`: lifecycle manager, connection pool, cleanup worker, status transition helpers, and event helper methods.
- `src/api/services/runs/__init__.py`: public run service exports.
- `src/api/routers/runs.py`: authenticated Run Center API.
- `src/ui/web/src/components/runs/RunStatusBadge.tsx`: compact Chinese status chip.
- `src/ui/web/src/components/runs/RunTimeline.tsx`: chronological event list.
- `src/ui/web/src/pages/AgentRunCenter.tsx`: task center page.

Modify:

- `src/api/app.py`: start and close RunManager, include `runs_router`.
- `src/api/services/approval/models.py`: add optional `run_id` to approval execution context and record.
- `src/api/services/approval/repository.py`: add nullable `run_id` column and persist it.
- `src/api/services/approval/gateway.py`: emit run events around approval lifecycle.
- `src/api/routers/approvals.py`: include run events when decisions resume workflows.
- `src/api/routers/chat.py`: create a run for chat execution and return `run_id`.
- `src/api/graphs/mcp_integrated_planner_graph.py`: bind run context, emit route/agent/checkpoint events, and check cooperative cancellation.
- `src/ui/web/src/services/api.ts`: add run types and `runAPI`.
- `src/ui/web/src/App.tsx`: add `/runs` route.
- `src/ui/web/src/components/Layout.tsx`: add "任务中心" navigation item.
- `src/ui/web/src/pages/ChatInterfaceNew.tsx`: carry `run_id` into assistant messages.
- `src/ui/web/src/components/chat/MessageBubble.tsx`: show a link to the run detail when present.

No test files are created in this phase because the user explicitly paused verification. A later verification phase should add focused backend repository/router tests and frontend component tests.

---

### Task 1: Run Domain Models And Context

**Files:**

- Create: `src/api/services/runs/models.py`
- Create: `src/api/services/runs/context.py`
- Create: `src/api/services/runs/__init__.py`

**Interfaces:**

- Produces: `RunStatus`, `RunType`, `RunEventType`, `RunEventSeverity`, `RunCancelled`, `RunRecord`, `RunEventRecord`, `RunCreate`, `RunUpdate`, `RunListFilters`, `RunListResponse`, `RunDetailResponse`, `RunEventResponse`, `RunRetryRequest`, `RunCancelRequest`.
- Produces: `RunExecutionContext(run_id, session_id, checkpoint_thread_id, request_id, user_id, username, user_role)`.
- Produces: `bind_run_context(context)`, `get_run_context()`.
- Consumed by: repository, manager, chat router, graph, approval gateway, and run router.

- [ ] **Step 1: Add model enums and records**

Create `src/api/services/runs/models.py` with these exported names:

```python
"""Domain models for durable agent run tracking."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


RUN_RETENTION = timedelta(days=30)


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"


class RunType(str, Enum):
    CHAT = "chat"
    AGENT = "agent"
    TOOL = "tool"
    RETRY = "retry"


class RunEventSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class RunEventType(str, Enum):
    RUN_CREATED = "run.created"
    RUN_STARTED = "run.started"
    ROUTE_SELECTED = "route.selected"
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
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
```

- [ ] **Step 2: Add typed payload models**

Append these model classes to `models.py`:

```python
@dataclass(frozen=True)
class RunExecutionContext:
    run_id: UUID
    session_id: str
    checkpoint_thread_id: str
    request_id: str
    user_id: int
    username: str
    user_role: str


class RunRecord(BaseModel):
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
```

- [ ] **Step 3: Add API request and response models**

Append these API models to `models.py`:

```python
class RunCreate(BaseModel):
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
    status: RunStatus | None = None
    current_agent: str | None = None
    current_tool: str | None = None
    risk_level: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    result_summary: str | None = None


class RunListFilters(BaseModel):
    status: RunStatus | None = None
    run_type: RunType | None = None
    user_id: int | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class RunCancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class RunRetryRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class RunEventResponse(RunEventRecord):
    pass


class RunDetailResponse(RunRecord):
    events: list[RunEventResponse] = Field(default_factory=list)


class RunListResponse(BaseModel):
    items: list[RunRecord]
    total: int
    page: int
    page_size: int
```

- [ ] **Step 4: Add context binding**

Create `src/api/services/runs/context.py`:

```python
"""Request-scoped run execution context."""

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from .models import RunExecutionContext


_run_context: ContextVar[RunExecutionContext | None] = ContextVar(
    "agent_run_execution_context",
    default=None,
)


@contextmanager
def bind_run_context(context: RunExecutionContext) -> Iterator[RunExecutionContext]:
    token = _run_context.set(context)
    try:
        yield context
    finally:
        _run_context.reset(token)


def get_run_context() -> RunExecutionContext | None:
    return _run_context.get()
```

- [ ] **Step 5: Add package exports**

Create `src/api/services/runs/__init__.py` with public exports from `context.py`, `manager.py`, `models.py`, and `repository.py`. If `manager.py` and `repository.py` do not exist yet during this task, include imports only for `context.py` and `models.py`, then expand the file in Task 3.

---

### Task 2: Run Repository

**Files:**

- Create: `src/api/services/runs/repository.py`
- Modify: `src/api/services/runs/__init__.py`

**Interfaces:**

- Consumes: `RunCreate`, `RunUpdate`, `RunListFilters`, `RunRecord`, `RunEventRecord`, `RunStatus`, `RunEventType`, `RunEventSeverity`.
- Produces: `RunRepository.setup()`, `create_run()`, `append_event()`, `update_run()`, `get_run()`, `list_runs()`, `list_events()`, `mark_cancel_requested()`, `create_retry_attempt()`, `delete_expired()`.

- [ ] **Step 1: Create repository class and schema setup**

Create `src/api/services/runs/repository.py` with `RunRepository.__init__(pool)` and `setup()` that creates:

```sql
CREATE TABLE IF NOT EXISTS agent_runs (
    run_id UUID PRIMARY KEY,
    session_id TEXT,
    checkpoint_thread_id TEXT,
    user_id BIGINT NOT NULL,
    username TEXT NOT NULL,
    user_role TEXT NOT NULL,
    run_type TEXT NOT NULL,
    title TEXT NOT NULL,
    input_summary TEXT,
    input_payload JSONB NOT NULL,
    status TEXT NOT NULL,
    current_agent TEXT,
    current_tool TEXT,
    risk_level TEXT,
    approval_count INTEGER NOT NULL DEFAULT 0,
    error_code TEXT,
    error_message TEXT,
    result_summary TEXT,
    retry_of_run_id UUID REFERENCES agent_runs(run_id),
    created_at TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT agent_runs_status_check CHECK (
        status IN (
            'queued', 'running', 'waiting_approval', 'completed',
            'failed', 'cancel_requested', 'cancelled'
        )
    ),
    CONSTRAINT agent_runs_type_check CHECK (
        run_type IN ('chat', 'agent', 'tool', 'retry')
    )
)
```

and:

```sql
CREATE TABLE IF NOT EXISTS agent_run_events (
    event_id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    agent_name TEXT,
    tool_name TEXT,
    approval_id UUID,
    checkpoint_id TEXT,
    message TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT agent_run_events_severity_check CHECK (
        severity IN ('info', 'warning', 'error')
    )
)
```

Create indexes:

```sql
CREATE INDEX IF NOT EXISTS agent_runs_status_created_idx
ON agent_runs (status, created_at DESC);

CREATE INDEX IF NOT EXISTS agent_runs_user_created_idx
ON agent_runs (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS agent_runs_session_created_idx
ON agent_runs (session_id, created_at DESC);

CREATE INDEX IF NOT EXISTS agent_run_events_run_created_idx
ON agent_run_events (run_id, created_at ASC, event_id ASC);
```

- [ ] **Step 2: Implement create and mapping helpers**

Implement:

```python
async def create_run(self, request: RunCreate) -> RunRecord
def _to_run_record(row: Any) -> RunRecord
def _to_event_record(row: Any) -> RunEventRecord
```

`create_run()` must insert `status='queued'`, `created_at=NOW()`, `updated_at=NOW()`, and `expires_at=NOW() + RUN_RETENTION`.

- [ ] **Step 3: Implement append_event**

Implement:

```python
async def append_event(
    self,
    *,
    run_id: UUID,
    event_type: RunEventType,
    message: str,
    severity: RunEventSeverity = RunEventSeverity.INFO,
    agent_name: str | None = None,
    tool_name: str | None = None,
    approval_id: UUID | None = None,
    checkpoint_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> RunEventRecord
```

The method inserts a UUID event row with `Jsonb(payload or {})`.

- [ ] **Step 4: Implement status updates**

Implement:

```python
async def update_run(self, run_id: UUID, update: RunUpdate) -> RunRecord
async def mark_started(self, run_id: UUID) -> RunRecord
async def mark_cancel_requested(self, run_id: UUID) -> RunRecord
```

Rules:

- `mark_started()` sets `status='running'`, `started_at=COALESCE(started_at, NOW())`.
- If setting a terminal status, set `completed_at=COALESCE(completed_at, NOW())`.
- `mark_cancel_requested()` only updates non-terminal statuses and returns the current row when already `cancel_requested`.

- [ ] **Step 5: Implement query methods**

Implement:

```python
async def get_run(self, run_id: UUID) -> RunRecord | None
async def list_events(self, run_id: UUID) -> list[RunEventRecord]
async def list_runs(
    self,
    filters: RunListFilters,
    *,
    requesting_user_id: int,
    can_view_all: bool,
) -> tuple[list[RunRecord], int]
```

`list_runs()` must scope to `user_id=requesting_user_id` unless `can_view_all` is true. If `can_view_all` is false, ignore `filters.user_id`.

- [ ] **Step 6: Implement retry and cleanup**

Implement:

```python
async def create_retry_attempt(
    self,
    original: RunRecord,
    *,
    requester_id: int,
    username: str,
    user_role: str,
    reason: str | None,
) -> RunRecord

async def delete_expired(self, limit: int = 500) -> int
```

`create_retry_attempt()` copies `session_id`, `checkpoint_thread_id`, sanitized `input_summary`, and sanitized `input_payload` from the original row, sets `run_type='retry'`, `retry_of_run_id=original.run_id`, and title `重试：{original.title}`.

---

### Task 3: Run Manager And Lifecycle

**Files:**

- Create: `src/api/services/runs/manager.py`
- Modify: `src/api/services/runs/__init__.py`
- Modify: `src/api/app.py`

**Interfaces:**

- Consumes: `RunRepository`.
- Produces: `RunManager.start()`, `RunManager.close()`, `RunManager.start_cleanup_worker()`, `get_run_manager()`, `emit_event()`, `mark_running()`, `mark_waiting_approval()`, `mark_completed()`, `mark_failed()`, `mark_cancelled()`, `request_cancel()`, `ensure_not_cancelled()`.

- [ ] **Step 1: Add manager pool lifecycle**

Create `src/api/services/runs/manager.py` following `ApprovalManager` style:

```python
class RunManager:
    def __init__(
        self,
        *,
        database_url: str | None = None,
        auto_setup: bool | str | None = None,
        pool_factory=AsyncConnectionPool,
        repository_factory=RunRepository,
    ) -> None:
        self._database_url = database_url
        self._auto_setup = auto_setup
        self._pool_factory = pool_factory
        self._repository_factory = repository_factory
        self._pool = None
        self._repository: RunRepository | None = None
        self._cleanup_task: asyncio.Task[None] | None = None
        self._started = False

    @property
    def repository(self) -> RunRepository:
        if not self._started or self._repository is None:
            raise RuntimeError("Run manager is not started")
        return self._repository

    async def start(self) -> None:
        if self._started:
            return
        database_url = self._resolve_database_url()
        pool = self._pool_factory(
            conninfo=database_url,
            min_size=1,
            max_size=3,
            kwargs={
                "autocommit": True,
                "prepare_threshold": 0,
                "row_factory": dict_row,
            },
            open=False,
        )
        await pool.open()
        await pool.wait()
        repository = self._repository_factory(pool)
        if self._resolve_auto_setup():
            await repository.setup()
        self._pool = pool
        self._repository = repository
        self._started = True

    async def close(self) -> None:
        cleanup_task = self._cleanup_task
        self._cleanup_task = None
        if cleanup_task is not None:
            cleanup_task.cancel()
            if cleanup_task is not asyncio.current_task():
                try:
                    await cleanup_task
                except asyncio.CancelledError:
                    pass
        if self._pool is not None:
            await self._pool.close()
        self._pool = None
        self._repository = None
        self._started = False
```

Resolve database URL in this order:

- `AGENT_RUN_DATABASE_URL`
- `LANGGRAPH_CHECKPOINT_DATABASE_URL`
- `_get_database_url()`

Resolve auto setup from `AGENT_RUN_AUTO_SETUP`, default `true`.

- [ ] **Step 2: Add event and status helper methods**

Implement these manager helpers:

```python
async def emit_event(
    self,
    *,
    run_id: UUID,
    event_type: RunEventType,
    message: str,
    severity: RunEventSeverity = RunEventSeverity.INFO,
    agent_name: str | None = None,
    tool_name: str | None = None,
    approval_id: UUID | None = None,
    checkpoint_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> RunEventRecord
async def mark_running(run_id: UUID) -> RunRecord
async def mark_waiting_approval(run_id: UUID, approval_id: UUID | None = None) -> RunRecord
async def mark_completed(run_id: UUID, result_summary: str | None = None) -> RunRecord
async def mark_failed(run_id: UUID, error: Exception | str, error_code: str | None = None) -> RunRecord
async def mark_cancelled(run_id: UUID, reason: str | None = None) -> RunRecord
async def request_cancel(run_id: UUID, reason: str | None = None) -> RunRecord
async def ensure_not_cancelled(run_id: UUID) -> None
```

`ensure_not_cancelled()` loads the run and raises `RunCancelled(run_id)` when status is `cancel_requested` or `cancelled`.

- [ ] **Step 3: Add cleanup worker**

Implement:

```python
def start_cleanup_worker(self) -> None
async def _run_cleanup_worker(self, interval_seconds: int) -> None
```

Read `AGENT_RUN_SWEEP_SECONDS`, default `3600`, and call `repository.delete_expired()` every interval.

- [ ] **Step 4: Wire app lifecycle**

In `src/api/app.py`:

- Import `runs_router` and `get_run_manager`.
- In startup, call `await run_manager.start()` after approval manager starts.
- Call `run_manager.start_cleanup_worker()`.
- In shutdown, call `await run_manager.close()` before checkpoint manager close.
- Include `app.include_router(runs_router)`.

- [ ] **Step 5: Expand package exports**

Update `src/api/services/runs/__init__.py` to export repository and manager names.

---

### Task 4: Run API Router

**Files:**

- Create: `src/api/routers/runs.py`
- Modify: `src/api/app.py` if not completed in Task 3

**Interfaces:**

- Consumes: `get_run_manager()`, `RunListFilters`, `RunListResponse`, `RunDetailResponse`, `RunCancelRequest`, `RunRetryRequest`.
- Produces endpoints:
  - `GET /api/v1/runs`
  - `GET /api/v1/runs/{run_id}`
  - `GET /api/v1/runs/{run_id}/events`
  - `POST /api/v1/runs/{run_id}/cancel`
  - `POST /api/v1/runs/{run_id}/retry`

- [ ] **Step 1: Add router and role helpers**

Create `src/api/routers/runs.py`:

```python
router = APIRouter(prefix="/api/v1", tags=["Agent Runs"])


def _can_view_all(current_user: CurrentUser) -> bool:
    return current_user.user.role in {UserRole.ADMIN, UserRole.MANAGER}


def _can_manage_run(current_user: CurrentUser, run: RunRecord) -> bool:
    return _can_view_all(current_user) or run.user_id == current_user.user.id
```

- [ ] **Step 2: Add list endpoint**

Implement:

```python
@router.get("/runs", response_model=RunListResponse)
async def list_runs(
    status: RunStatus | None = None,
    run_type: RunType | None = None,
    user_id: int | None = None,
    date_from: datetime | None = Query(default=None, alias="from"),
    date_to: datetime | None = Query(default=None, alias="to"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user_context),
) -> RunListResponse:
    manager = get_run_manager()
    filters = RunListFilters(
        status=status,
        run_type=run_type,
        user_id=user_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    items, total = await manager.repository.list_runs(
        filters,
        requesting_user_id=current_user.user.id,
        can_view_all=_can_view_all(current_user),
    )
    return RunListResponse(items=items, total=total, page=page, page_size=page_size)
```

- [ ] **Step 3: Add detail and events endpoints**

Implement 404/403 behavior:

```python
@router.get("/runs/{run_id}", response_model=RunDetailResponse)
async def get_run(
    run_id: UUID,
    current_user: CurrentUser = Depends(get_current_user_context),
) -> RunDetailResponse

@router.get("/runs/{run_id}/events", response_model=list[RunEventResponse])
async def get_run_events(
    run_id: UUID,
    current_user: CurrentUser = Depends(get_current_user_context),
) -> list[RunEventResponse]
```

- [ ] **Step 4: Add cancel endpoint**

Implement:

```python
@router.post("/runs/{run_id}/cancel", response_model=RunDetailResponse)
async def cancel_run(
    run_id: UUID,
    request: RunCancelRequest,
    current_user: CurrentUser = Depends(get_current_user_context),
) -> RunDetailResponse:
    manager = get_run_manager()
    run = await _load_visible_run(run_id, current_user)
    if run.status in TERMINAL_STATUSES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Run is already terminal")
    updated = await manager.request_cancel(run_id, request.reason)
    events = await manager.repository.list_events(run_id)
    return RunDetailResponse(**updated.model_dump(), events=events)
```

Return 409 when run is terminal.

- [ ] **Step 5: Add retry endpoint**

Implement:

```python
@router.post("/runs/{run_id}/retry", response_model=RunDetailResponse)
async def retry_run(
    run_id: UUID,
    request: RunRetryRequest,
    current_user: CurrentUser = Depends(get_current_user_context),
) -> RunDetailResponse:
    manager = get_run_manager()
    run = await _load_visible_run(run_id, current_user)
    if run.status is not RunStatus.FAILED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only failed runs can be retried")
    retry = await manager.repository.create_retry_attempt(
        run,
        requester_id=current_user.user.id,
        username=current_user.user.username,
        user_role=current_user.user.role.value,
        reason=request.reason,
    )
    await manager.emit_event(
        run_id=retry.run_id,
        event_type=RunEventType.RUN_RETRY_REQUESTED,
        message="已创建重试任务",
        payload={"retry_of_run_id": str(run.run_id), "reason": request.reason},
    )
    events = await manager.repository.list_events(retry.run_id)
    return RunDetailResponse(**retry.model_dump(), events=events)
```

Return 409 unless original run status is `failed`. This endpoint creates the retry ledger row and event; replay execution is outside the current feature-code scope and remains a separate implementation decision.

---

### Task 5: Approval Linkage

**Files:**

- Modify: `src/api/services/approval/models.py`
- Modify: `src/api/services/approval/repository.py`
- Modify: `src/api/services/approval/gateway.py`
- Modify: `src/api/routers/approvals.py`
- Modify: `src/api/graphs/mcp_integrated_planner_graph.py`

**Interfaces:**

- Consumes: `get_run_context()`, `get_run_manager()`.
- Produces: approval records with nullable `run_id`; run events for requested/approved/rejected/expired/executed/failed approvals.

- [ ] **Step 1: Add run_id to approval models**

In `ApprovalExecutionContext`, add:

```python
run_id: UUID | None = None
```

In `ApprovalRecord`, add:

```python
run_id: UUID | None = None
```

Import `UUID` is already present in `models.py`.

- [ ] **Step 2: Add nullable approval column**

In `ApprovalRepository.setup()`, add:

```sql
ALTER TABLE langgraph_approvals
ADD COLUMN IF NOT EXISTS run_id UUID
```

Add index:

```sql
CREATE INDEX IF NOT EXISTS langgraph_approvals_run_idx
ON langgraph_approvals (run_id, created_at DESC)
```

Update `ensure_pending()` insert column list and values to include `context.run_id`.

- [ ] **Step 3: Emit approval requested and waiting events**

In `ApprovalGateway.execute()`, after `ensure_pending()` returns `record`, call the run manager when `record.run_id` is present:

```python
await run_manager.mark_waiting_approval(record.run_id, record.approval_id)
await run_manager.emit_event(
    run_id=record.run_id,
    event_type=RunEventType.APPROVAL_REQUESTED,
    message=f"需要审批：{record.tool_name}",
    approval_id=record.approval_id,
    tool_name=record.tool_name,
    payload={"action": record.action_key, "risk_reasons": record.risk_reasons},
)
```

If event writing fails, raise `ApprovalConflictError` before executing the risky tool.

- [ ] **Step 4: Emit decision events**

In `ApprovalGateway.execute()`:

- Before raising `ApprovalRejectedError`, emit `approval.rejected`.
- After `claim_approved_execution()`, emit `approval.approved`.
- After `mark_executed()`, emit `tool.completed` and return the result.
- In the executor exception path, emit `run.failed` through manager after `mark_failed()`.

- [ ] **Step 5: Preserve run context on approval resume**

In `MCPPlannerGraph.resume_approval()`, when constructing `ApprovalExecutionContext`, pass `run_id=record.run_id`.

If `record.run_id` is present, bind run context around the graph resume with:

```python
RunExecutionContext(
    run_id=record.run_id,
    session_id=record.thread_id,
    checkpoint_thread_id=record.thread_id,
    request_id=record.request_id,
    user_id=record.requester_id,
    username=record.requester_username,
    user_role="unknown",
)
```

Use this only to preserve event linkage; authorization still comes from authenticated API dependencies.

---

### Task 6: Chat And Graph Instrumentation

**Files:**

- Modify: `src/api/routers/chat.py`
- Modify: `src/api/graphs/mcp_integrated_planner_graph.py`

**Interfaces:**

- Consumes: `get_run_manager()`, `bind_run_context()`, `RunExecutionContext`, `RunCancelled`.
- Produces: `ChatResponse.run_id`, run creation on chat requests, route/agent/completion/failure/cancellation events.

- [ ] **Step 1: Add run_id to chat response**

In `ChatResponse`, add:

```python
run_id: Optional[str] = None
```

Update fallback response helpers to accept optional `run_id: str | None = None` and include it.

- [ ] **Step 2: Create run before planner execution**

Inside `chat()` after `request_id` is created, call:

```python
run_record = await get_run_manager().repository.create_run(
    RunCreate(
        session_id=session_id,
        checkpoint_thread_id=session_id,
        user_id=current_user.user.id,
        username=current_user.user.username,
        user_role=current_user.user.role.value,
        run_type=RunType.CHAT,
        title=_summarize_run_title(req.message),
        input_summary=_summarize_run_title(req.message),
        input_payload={
            "message": req.message,
            "session_id": session_id,
            "context": _sanitize_run_payload(req.context or {}),
            "enable_reasoning": req.enable_reasoning,
            "reasoning_types": req.reasoning_types or [],
        },
    )
)
```

Add local helper `_summarize_run_title(message: str) -> str` that returns the first 60 non-null characters or `智能体任务`.

- [ ] **Step 3: Bind run context around `process_query()`**

Wrap the deduplicated execution body in:

```python
run_context = RunExecutionContext(
    run_id=run_record.run_id,
    session_id=session_id,
    checkpoint_thread_id=session_id,
    request_id=request_id,
    user_id=current_user.user.id,
    username=current_user.user.username,
    user_role=current_user.user.role.value,
)
with bind_run_context(run_context):
    result = await process_query()
```

Pass `run_id=run_record.run_id` into `ApprovalExecutionContext`.

- [ ] **Step 4: Mark run statuses in chat**

Use manager methods:

- `mark_running()` before planner invocation.
- `mark_waiting_approval()` when response status is `approval_required`.
- `mark_completed()` when a normal response is created.
- `mark_failed()` in error paths.
- `mark_completed()` for cache hits with result summary `命中缓存`.

Every returned `ChatResponse` must include `run_id=str(run_record.run_id)` except responses served before run creation.

- [ ] **Step 5: Add graph event helpers**

In `mcp_integrated_planner_graph.py`, import run helpers and add:

```python
async def _emit_run_event(
    event_type: RunEventType,
    message: str,
    *,
    severity: RunEventSeverity = RunEventSeverity.INFO,
    agent_name: str | None = None,
    tool_name: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    context = get_run_context()
    if context is None:
        return
    await get_run_manager().emit_event(
        run_id=context.run_id,
        event_type=event_type,
        message=message,
        severity=severity,
        agent_name=agent_name,
        tool_name=tool_name,
        payload=payload,
    )


async def _check_run_cancelled() -> None:
    context = get_run_context()
    if context is not None:
        await get_run_manager().ensure_not_cancelled(context.run_id)
```

`_check_run_cancelled()` gets `get_run_context()`, then calls `get_run_manager().ensure_not_cancelled(context.run_id)`.

- [ ] **Step 6: Instrument graph nodes**

At the start of `_mcp_route_intent()`, call `_check_run_cancelled()`.

After route selection is known, emit:

```python
RunEventType.ROUTE_SELECTED
message=f"路由到：{state.get('routing_decision') or 'unknown'}"
```

At the start and end of each `_mcp_*_agent()` node, emit `agent.started` and `agent.completed` with the agent name.

At the start of `_mcp_synthesize_response()`, call `_check_run_cancelled()`.

- [ ] **Step 7: Handle cancellation cleanly**

In `process_warehouse_query()`, catch `RunCancelled` and return:

```python
{
    "response": "任务已取消。",
    "intent": "cancelled",
    "route": "cancelled",
    "session_id": session_id,
    "context": {},
    "execution_status": "cancelled",
}
```

Also call `await get_run_manager().mark_cancelled(context.run_id, "图执行观察到取消请求")` when a run context is available.

---

### Task 7: Frontend API Types

**Files:**

- Modify: `src/ui/web/src/services/api.ts`

**Interfaces:**

- Produces: `AgentRun`, `AgentRunEvent`, `AgentRunStatus`, `RunListResponse`, `runAPI`.
- Consumed by: `AgentRunCenter.tsx`, chat messages, run timeline.

- [ ] **Step 1: Add run types**

Append near the existing API interfaces:

```typescript
export type AgentRunStatus =
  | 'queued'
  | 'running'
  | 'waiting_approval'
  | 'completed'
  | 'failed'
  | 'cancel_requested'
  | 'cancelled';

export interface AgentRun {
  run_id: string;
  session_id?: string | null;
  checkpoint_thread_id?: string | null;
  user_id: number;
  username: string;
  user_role: string;
  run_type: 'chat' | 'agent' | 'tool' | 'retry';
  title: string;
  input_summary?: string | null;
  status: AgentRunStatus;
  current_agent?: string | null;
  current_tool?: string | null;
  risk_level?: string | null;
  approval_count: number;
  error_code?: string | null;
  error_message?: string | null;
  result_summary?: string | null;
  retry_of_run_id?: string | null;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  updated_at: string;
  expires_at: string;
}
```

- [ ] **Step 2: Add event and list types**

```typescript
export interface AgentRunEvent {
  event_id: string;
  run_id: string;
  event_type: string;
  severity: 'info' | 'warning' | 'error';
  agent_name?: string | null;
  tool_name?: string | null;
  approval_id?: string | null;
  checkpoint_id?: string | null;
  message: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface AgentRunDetail extends AgentRun {
  events: AgentRunEvent[];
}

export interface AgentRunListResponse {
  items: AgentRun[];
  total: number;
  page: number;
  page_size: number;
}
```

- [ ] **Step 3: Add run API client**

Add:

```typescript
export const runAPI = {
  list: async (params: {
    status?: AgentRunStatus | '';
    page?: number;
    page_size?: number;
  } = {}): Promise<AgentRunListResponse> => {
    const response = await api.get('/runs', { params });
    return response.data;
  },

  get: async (runId: string): Promise<AgentRunDetail> => {
    const safeId = validatePathParam(runId, 'run_id');
    const response = await api.get(`/runs/${safeId}`);
    return response.data;
  },

  events: async (runId: string): Promise<AgentRunEvent[]> => {
    const safeId = validatePathParam(runId, 'run_id');
    const response = await api.get(`/runs/${safeId}/events`);
    return response.data;
  },

  cancel: async (runId: string, reason?: string): Promise<AgentRunDetail> => {
    const safeId = validatePathParam(runId, 'run_id');
    const response = await api.post(`/runs/${safeId}/cancel`, { reason });
    return response.data;
  },

  retry: async (runId: string, reason?: string): Promise<AgentRunDetail> => {
    const safeId = validatePathParam(runId, 'run_id');
    const response = await api.post(`/runs/${safeId}/retry`, { reason });
    return response.data;
  },
};
```

- [ ] **Step 4: Add run_id to chat response type**

Add to `ChatResponse`:

```typescript
run_id?: string | null;
```

---

### Task 8: Frontend Run Center UI

**Files:**

- Create: `src/ui/web/src/components/runs/RunStatusBadge.tsx`
- Create: `src/ui/web/src/components/runs/RunTimeline.tsx`
- Create: `src/ui/web/src/pages/AgentRunCenter.tsx`
- Modify: `src/ui/web/src/App.tsx`
- Modify: `src/ui/web/src/components/Layout.tsx`

**Interfaces:**

- Consumes: `runAPI`, `AgentRun`, `AgentRunEvent`.
- Produces: `/runs` page with list, filters, detail panel, timeline, cancel, retry, and approval jump.

- [ ] **Step 1: Add status badge**

Create `RunStatusBadge.tsx`:

```tsx
import React from 'react';
import { Chip } from '@mui/material';
import { AgentRunStatus } from '../../services/api';

const statusMap: Record<AgentRunStatus, { label: string; color: 'default' | 'primary' | 'success' | 'warning' | 'error' | 'info' }> = {
  queued: { label: '排队中', color: 'default' },
  running: { label: '执行中', color: 'primary' },
  waiting_approval: { label: '待审批', color: 'warning' },
  completed: { label: '已完成', color: 'success' },
  failed: { label: '失败', color: 'error' },
  cancel_requested: { label: '取消中', color: 'info' },
  cancelled: { label: '已取消', color: 'default' },
};

interface Props {
  status: AgentRunStatus;
}

const RunStatusBadge: React.FC<Props> = ({ status }) => {
  const item = statusMap[status] || statusMap.queued;
  return <Chip size="small" label={item.label} color={item.color} />;
};

export default RunStatusBadge;
```

- [ ] **Step 2: Add timeline component**

Create `RunTimeline.tsx` with Material UI `List`, `ListItem`, `ListItemText`, and `Chip`. Render each event message, event type, time, agent/tool/approval ID when present. Use Chinese empty state `暂无事件`.

- [ ] **Step 3: Add page state and list query**

Create `AgentRunCenter.tsx`:

- Use `useQuery({ queryKey: ['agent-runs', status, page], queryFn: () => runAPI.list({ status, page, page_size: 20 }) })`.
- Keep `selectedRunId`, `status`, `page`, and `snackbar` state.
- On row click, set selected run and fetch detail with `runAPI.get(selectedRunId)`.

- [ ] **Step 4: Add operations**

Use React Query mutations:

- `cancelMutation` calls `runAPI.cancel(run_id, '用户在任务中心请求取消')`.
- `retryMutation` calls `runAPI.retry(run_id, '用户在任务中心请求重试')`.
- On success, invalidate `['agent-runs']` and `['agent-run-detail', run_id]`.

Show:

- `取消` button when status is not `completed`, `failed`, or `cancelled`.
- `重试` button when status is `failed`.
- `去审批` button when status is `waiting_approval`; it navigates to `/chat`.

- [ ] **Step 5: Add route**

In `App.tsx`:

```tsx
import AgentRunCenter from './pages/AgentRunCenter';
<Route path="/runs" element={<AgentRunCenter />} />
```

- [ ] **Step 6: Add navigation**

In `Layout.tsx`, import `AssignmentTurnedIn as AssignmentTurnedInIcon` from `@mui/icons-material` and add:

```tsx
{ text: '任务中心', icon: <AssignmentTurnedInIcon />, path: '/runs' }
```

---

### Task 9: Chat Run Links

**Files:**

- Modify: `src/ui/web/src/pages/ChatInterfaceNew.tsx`
- Modify: `src/ui/web/src/components/chat/MessageBubble.tsx`

**Interfaces:**

- Consumes: `ChatResponse.run_id`.
- Produces: assistant messages with `run_id`, rendered link to `/runs?run_id=<id>`.

- [ ] **Step 1: Extend chat message type**

In `ChatInterfaceNew.tsx` local `Message` interface, add:

```typescript
run_id?: string | null;
```

- [ ] **Step 2: Store run_id when creating assistant messages**

In `simulateStreamingResponse(response)`, add:

```typescript
run_id: response.run_id,
```

to `assistantMessage`.

Also add `run_id` to fallback assistant messages and approval workflow messages when workflow responses include it later.

- [ ] **Step 3: Extend MessageBubble props**

In `MessageBubble.tsx`, add `run_id?: string | null` to the message prop type and import `Link as RouterLink` from `react-router-dom`.

- [ ] **Step 4: Render run link**

After the message content, render:

```tsx
{message.run_id && (
  <Button
    component={RouterLink}
    to={`/runs?run_id=${encodeURIComponent(message.run_id)}`}
    size="small"
    sx={{ mt: 1, color: isUser ? 'primary.contrastText' : 'primary.main' }}
  >
    查看任务记录
  </Button>
)}
```

---

## Deferred Verification Plan

When the user asks to verify, run these checks in order:

1. Backend import check for `src.api.app`.
2. Backend API smoke check against `/api/v1/runs`.
3. Frontend type check.
4. Frontend build.
5. Browser check for `/runs`.
6. Manual chat flow check that returns `run_id`.
7. Manual approval flow check that links `approval_id` and `run_id`.

Do not run these checks during the current feature-code-only phase.
