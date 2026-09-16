"""PostgreSQL persistence for durable agent run tracking."""

from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from .models import (
    RUN_RETENTION,
    TERMINAL_STATUSES,
    RunCreate,
    RunEventRecord,
    RunEventSeverity,
    RunEventType,
    RunListFilters,
    RunRecord,
    RunStatus,
    RunType,
    RunUpdate,
)


class RunRepository:
    """Store run ledger rows and append-only timeline events."""

    def __init__(self, pool) -> None:
        self._pool = pool

    async def setup(self) -> None:
        """Create run tables and indexes when absent."""

        statements = (
            """
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
            """,
            """
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
            """,
            """
            CREATE INDEX IF NOT EXISTS agent_runs_status_created_idx
            ON agent_runs (status, created_at DESC)
            """,
            """
            CREATE INDEX IF NOT EXISTS agent_runs_user_created_idx
            ON agent_runs (user_id, created_at DESC)
            """,
            """
            CREATE INDEX IF NOT EXISTS agent_runs_session_created_idx
            ON agent_runs (session_id, created_at DESC)
            """,
            """
            CREATE INDEX IF NOT EXISTS agent_runs_retry_of_idx
            ON agent_runs (retry_of_run_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS agent_run_events_run_created_idx
            ON agent_run_events (run_id, created_at ASC, event_id ASC)
            """,
        )
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                for statement in statements:
                    await cursor.execute(statement)

    async def create_run(self, request: RunCreate) -> RunRecord:
        """Insert a new queued run and its creation event."""

        run_id = uuid4()
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    INSERT INTO agent_runs (
                        run_id, session_id, checkpoint_thread_id, user_id,
                        username, user_role, run_type, title, input_summary,
                        input_payload, status, retry_of_run_id, created_at,
                        updated_at, expires_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        'queued', %s, NOW(), NOW(), NOW() + %s
                    )
                    RETURNING *
                    """,
                    (
                        run_id,
                        request.session_id,
                        request.checkpoint_thread_id,
                        request.user_id,
                        request.username,
                        request.user_role,
                        request.run_type.value,
                        request.title,
                        request.input_summary,
                        Jsonb(request.input_payload),
                        request.retry_of_run_id,
                        RUN_RETENTION,
                    ),
                )
                row = await cursor.fetchone()

        record = _require_run(row)
        await self.append_event(
            run_id=record.run_id,
            event_type=RunEventType.RUN_CREATED,
            message="任务已创建",
            payload={"title": record.title, "run_type": record.run_type.value},
        )
        return record

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
    ) -> RunEventRecord:
        """Append a timeline event for one run."""

        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    INSERT INTO agent_run_events (
                        event_id, run_id, event_type, severity, agent_name,
                        tool_name, approval_id, checkpoint_id, message,
                        payload, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
                    )
                    RETURNING *
                    """,
                    (
                        uuid4(),
                        run_id,
                        event_type.value,
                        severity.value,
                        agent_name,
                        tool_name,
                        approval_id,
                        checkpoint_id,
                        message,
                        Jsonb(payload or {}),
                    ),
                )
                row = await cursor.fetchone()
        return _require_event(row)

    async def update_run(self, run_id: UUID, update: RunUpdate) -> RunRecord:
        """Apply a partial update to mutable run fields."""

        values: list[Any] = []
        assignments: list[str] = []
        payload = update.model_dump(exclude_none=True)
        for field, value in payload.items():
            if isinstance(value, RunStatus):
                value = value.value
            assignments.append(f"{field} = %s")
            values.append(value)

        if update.status in TERMINAL_STATUSES:
            assignments.append("completed_at = COALESCE(completed_at, NOW())")
        assignments.append("updated_at = NOW()")
        values.append(run_id)

        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    f"""
                    UPDATE agent_runs
                    SET {", ".join(assignments)}
                    WHERE run_id = %s
                    RETURNING *
                    """,
                    tuple(values),
                )
                row = await cursor.fetchone()
        return _require_run(row)

    async def mark_started(self, run_id: UUID) -> RunRecord:
        """Mark a queued run as running."""

        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    UPDATE agent_runs
                    SET status = 'running',
                        started_at = COALESCE(started_at, NOW()),
                        updated_at = NOW()
                    WHERE run_id = %s
                    RETURNING *
                    """,
                    (run_id,),
                )
                row = await cursor.fetchone()
        return _require_run(row)

    async def mark_waiting_approval(
        self,
        run_id: UUID,
        *,
        approval_id: UUID | None = None,
    ) -> RunRecord:
        """Mark a run as waiting for human approval."""

        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    UPDATE agent_runs
                    SET status = 'waiting_approval',
                        approval_count = approval_count + %s,
                        updated_at = NOW()
                    WHERE run_id = %s
                    RETURNING *
                    """,
                    (1 if approval_id is not None else 0, run_id),
                )
                row = await cursor.fetchone()
        return _require_run(row)

    async def mark_cancel_requested(self, run_id: UUID) -> RunRecord:
        """Request cooperative cancellation for a non-terminal run."""

        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    UPDATE agent_runs
                    SET status = CASE
                            WHEN status IN ('completed', 'failed', 'cancelled')
                                THEN status
                            ELSE 'cancel_requested'
                        END,
                        updated_at = NOW()
                    WHERE run_id = %s
                    RETURNING *
                    """,
                    (run_id,),
                )
                row = await cursor.fetchone()
        return _require_run(row)

    async def get_run(self, run_id: UUID) -> RunRecord | None:
        """Load one run by ID."""

        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT * FROM agent_runs WHERE run_id = %s",
                    (run_id,),
                )
                row = await cursor.fetchone()
        return _to_run_record(row) if row is not None else None

    async def list_events(self, run_id: UUID) -> list[RunEventRecord]:
        """Return a run's event timeline in chronological order."""

        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT * FROM agent_run_events
                    WHERE run_id = %s
                    ORDER BY created_at ASC, event_id ASC
                    """,
                    (run_id,),
                )
                rows = await cursor.fetchall()
        return [_to_event_record(row) for row in rows]

    async def list_runs(
        self,
        filters: RunListFilters,
        *,
        requesting_user_id: int,
        can_view_all: bool,
    ) -> tuple[list[RunRecord], int]:
        """List runs with role-aware scoping."""

        conditions: list[str] = []
        values: list[Any] = []
        if not can_view_all:
            conditions.append("user_id = %s")
            values.append(requesting_user_id)
        elif filters.user_id is not None:
            conditions.append("user_id = %s")
            values.append(filters.user_id)
        if filters.status is not None:
            conditions.append("status = %s")
            values.append(filters.status.value)
        if filters.run_type is not None:
            conditions.append("run_type = %s")
            values.append(filters.run_type.value)
        if filters.date_from is not None:
            conditions.append("created_at >= %s")
            values.append(filters.date_from)
        if filters.date_to is not None:
            conditions.append("created_at <= %s")
            values.append(filters.date_to)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        offset = (filters.page - 1) * filters.page_size
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    f"SELECT COUNT(*) AS total FROM agent_runs {where_clause}",
                    tuple(values),
                )
                count_row = await cursor.fetchone()
                await cursor.execute(
                    f"""
                    SELECT * FROM agent_runs
                    {where_clause}
                    ORDER BY created_at DESC, run_id DESC
                    LIMIT %s OFFSET %s
                    """,
                    tuple(values + [filters.page_size, offset]),
                )
                rows = await cursor.fetchall()

        total = int(count_row["total"]) if count_row is not None else 0
        return [_to_run_record(row) for row in rows], total

    async def create_retry_attempt(
        self,
        original: RunRecord,
        *,
        requester_id: int,
        username: str,
        user_role: str,
        reason: str | None,
    ) -> RunRecord:
        """Create a new queued retry row for a failed run."""

        retry = await self.create_run(
            RunCreate(
                session_id=original.session_id,
                checkpoint_thread_id=original.checkpoint_thread_id,
                user_id=requester_id,
                username=username,
                user_role=user_role,
                run_type=RunType.RETRY,
                title=f"重试：{original.title}",
                input_summary=original.input_summary,
                input_payload={
                    **original.input_payload,
                    "retry_reason": reason,
                    "retry_of_run_id": str(original.run_id),
                },
                retry_of_run_id=original.run_id,
            )
        )
        return retry

    async def delete_expired(self, limit: int = 500) -> int:
        """Delete expired run rows and their cascade events."""

        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    WITH expired AS (
                        SELECT run_id
                        FROM agent_runs
                        WHERE expires_at <= NOW()
                        ORDER BY expires_at ASC, run_id ASC
                        LIMIT %s
                    )
                    DELETE FROM agent_runs
                    USING expired
                    WHERE agent_runs.run_id = expired.run_id
                    """,
                    (limit,),
                )
                return int(cursor.rowcount or 0)


def _to_run_record(row: Any) -> RunRecord:
    return RunRecord.model_validate(row)


def _to_event_record(row: Any) -> RunEventRecord:
    return RunEventRecord.model_validate(row)


def _require_run(row: Any | None) -> RunRecord:
    if row is None:
        raise RuntimeError("Run record was not found")
    return _to_run_record(row)


def _require_event(row: Any | None) -> RunEventRecord:
    if row is None:
        raise RuntimeError("Run event was not created")
    return _to_event_record(row)
