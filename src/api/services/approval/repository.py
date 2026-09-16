"""PostgreSQL persistence for durable human approval records."""

import json
import re
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from .models import (
    APPROVAL_TTL,
    ApprovalConflictError,
    ApprovalDecision,
    ApprovalExecutionContext,
    ApprovalRecord,
    ApprovalResumePayload,
    ApprovalStatus,
    RiskAssessment,
)


_CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|access[_-]?key)\b"
    r"(\s*[:=]\s*)([^\s,;&]+)"
)
_AUTHORIZATION_VALUE = re.compile(
    r"(?i)\b(authorization\s*[:=]\s*)(?:bearer|basic)?\s*[^\s,;&]+"
)
_BEARER_VALUE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")


class ApprovalRepository:
    """Store and atomically transition approval lifecycle records."""

    def __init__(self, pool) -> None:
        self._pool = pool

    async def setup(self) -> None:
        """Create the approval table and its lookup indexes when absent."""

        statements = (
            """
            CREATE TABLE IF NOT EXISTS langgraph_approvals (
                approval_id UUID PRIMARY KEY,
                thread_id TEXT NOT NULL,
                checkpoint_ns TEXT NOT NULL,
                request_id TEXT NOT NULL,
                action_key TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                tool_key TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                arguments JSONB NOT NULL,
                risk_level TEXT NOT NULL,
                risk_reasons JSONB NOT NULL,
                requester_id BIGINT NOT NULL,
                requester_username TEXT NOT NULL,
                run_id UUID,
                approver_id BIGINT,
                approver_username TEXT,
                decision_reason TEXT,
                status TEXT NOT NULL,
                result JSONB,
                error TEXT,
                created_at TIMESTAMPTZ NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL,
                decided_at TIMESTAMPTZ,
                execution_started_at TIMESTAMPTZ,
                executed_at TIMESTAMPTZ,
                updated_at TIMESTAMPTZ NOT NULL,
                CONSTRAINT langgraph_approvals_status_check CHECK (
                    status IN (
                        'pending', 'approved', 'executing', 'executed',
                        'rejected', 'expired', 'failed'
                    )
                ),
                CONSTRAINT langgraph_approvals_risk_check CHECK (
                    risk_level IN ('high', 'unknown')
                )
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS langgraph_approvals_status_expires_idx
            ON langgraph_approvals (status, expires_at)
            """,
            """
            CREATE INDEX IF NOT EXISTS langgraph_approvals_thread_checkpoint_idx
            ON langgraph_approvals (thread_id, checkpoint_ns, created_at DESC)
            """,
            """
            ALTER TABLE langgraph_approvals
            ADD COLUMN IF NOT EXISTS run_id UUID
            """,
            """
            CREATE INDEX IF NOT EXISTS langgraph_approvals_run_idx
            ON langgraph_approvals (run_id, created_at DESC)
            """,
        )
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                for statement in statements:
                    await cursor.execute(statement)

    async def ensure_pending(
        self,
        context: ApprovalExecutionContext,
        tool_key: str,
        tool_name: str,
        arguments: dict[str, Any],
        action_index: int,
        risk: RiskAssessment,
    ) -> ApprovalRecord:
        """Create one pending record per canonical action or return the existing row."""

        if risk.risk_level not in {"high", "unknown"}:
            raise ValueError("Only high or unknown risk actions can require approval")

        canonical_arguments = _canonical_json(arguments, label="arguments")
        action_key = f"{context.request_id}:{action_index}:{tool_key}"
        idempotency_key = sha256(
            (
                f"{context.thread_id}:{context.checkpoint_ns}:"
                f"{action_key}:{canonical_arguments}"
            ).encode("utf-8")
        ).hexdigest()

        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    INSERT INTO langgraph_approvals (
                        approval_id, thread_id, checkpoint_ns, request_id,
                        action_key, idempotency_key, tool_key, tool_name,
                        arguments, risk_level, risk_reasons, requester_id,
                        requester_username, run_id, status, created_at,
                        expires_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, 'pending', NOW(), NOW() + %s, NOW()
                    )
                    ON CONFLICT (idempotency_key) DO NOTHING
                    """,
                    (
                        uuid4(),
                        context.thread_id,
                        context.checkpoint_ns,
                        context.request_id,
                        action_key,
                        idempotency_key,
                        tool_key,
                        tool_name,
                        Jsonb(arguments),
                        risk.risk_level,
                        Jsonb(list(risk.reasons)),
                        context.requester_id,
                        context.requester_username,
                        context.run_id,
                        APPROVAL_TTL,
                    ),
                )
                await cursor.execute(
                    """
                    SELECT * FROM langgraph_approvals
                    WHERE idempotency_key = %s
                    """,
                    (idempotency_key,),
                )
                row = await cursor.fetchone()

        if row is None:
            raise RuntimeError("Approval record could not be created or loaded")
        return _to_record(row)

    async def get(self, approval_id: UUID) -> ApprovalRecord | None:
        """Load an approval record by its identifier."""

        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT * FROM langgraph_approvals WHERE approval_id = %s",
                    (approval_id,),
                )
                row = await cursor.fetchone()
        return _to_record(row) if row is not None else None

    async def list_pending(self, limit: int = 100) -> list[ApprovalRecord]:
        """List pending approvals in stable creation order."""

        limit = _positive_limit(limit)
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT * FROM langgraph_approvals
                    WHERE status = 'pending'
                    ORDER BY created_at ASC, approval_id ASC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = await cursor.fetchall()
        return [_to_record(row) for row in rows]

    async def record_rejection(
        self,
        approval_id: UUID,
        resume_payload: ApprovalResumePayload,
        *,
        expired: bool = False,
    ) -> ApprovalRecord:
        """Atomically deny a pending action, with replay-safe terminal behavior."""

        _validate_resume_payload(approval_id, resume_payload)
        if not expired and resume_payload.decision is not ApprovalDecision.REJECT:
            raise ApprovalConflictError("A rejection transition requires a reject decision")

        target_status = ApprovalStatus.EXPIRED if expired else ApprovalStatus.REJECTED
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    UPDATE langgraph_approvals
                    SET status = %s,
                        approver_id = %s,
                        approver_username = %s,
                        decision_reason = %s,
                        decided_at = NOW(),
                        updated_at = NOW()
                    WHERE approval_id = %s AND status = 'pending'
                    RETURNING *
                    """,
                    (
                        target_status.value,
                        resume_payload.approver_id,
                        resume_payload.approver_username,
                        resume_payload.reason,
                        approval_id,
                    ),
                )
                row = await cursor.fetchone()
                if row is None:
                    row = await self._fetch_with_cursor(cursor, approval_id)

        record = _require_record(row)
        if record.status is target_status:
            return record
        raise ApprovalConflictError(
            f"Approval cannot transition from {record.status.value} to {target_status.value}"
        )

    async def claim_approved_execution(
        self,
        approval_id: UUID,
        resume_payload: ApprovalResumePayload,
    ) -> ApprovalRecord:
        """Claim an approved action exactly once before its target tool executes."""

        _validate_resume_payload(approval_id, resume_payload)
        if resume_payload.decision is not ApprovalDecision.APPROVE:
            raise ApprovalConflictError("An execution claim requires an approve decision")

        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    UPDATE langgraph_approvals
                    SET status = 'executing',
                        approver_id = %s,
                        approver_username = %s,
                        decision_reason = %s,
                        decided_at = COALESCE(decided_at, NOW()),
                        execution_started_at = NOW(),
                        updated_at = NOW()
                    WHERE approval_id = %s
                      AND status IN ('pending', 'approved')
                      AND expires_at > NOW()
                    RETURNING *
                    """,
                    (
                        resume_payload.approver_id,
                        resume_payload.approver_username,
                        resume_payload.reason,
                        approval_id,
                    ),
                )
                row = await cursor.fetchone()
                claimed_execution = row is not None
                if row is None:
                    row = await self._fetch_with_cursor(cursor, approval_id)

        record = _require_record(row)
        if claimed_execution:
            return record
        if record.status is ApprovalStatus.EXECUTED:
            return record
        if record.status is ApprovalStatus.EXECUTING:
            raise ApprovalConflictError(
                "Approval execution is already in progress and cannot be retried"
            )
        raise ApprovalConflictError(
            f"Approval in {record.status.value} state cannot be claimed for execution"
        )

    async def mark_executed(self, approval_id: UUID, result: Any) -> ApprovalRecord:
        """Persist a JSON-safe result for the currently executing action."""

        _canonical_json(result, label="result")
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    UPDATE langgraph_approvals
                    SET status = 'executed',
                        result = %s,
                        error = NULL,
                        executed_at = NOW(),
                        updated_at = NOW()
                    WHERE approval_id = %s AND status = 'executing'
                    RETURNING *
                    """,
                    (Jsonb(result), approval_id),
                )
                row = await cursor.fetchone()
                if row is None:
                    row = await self._fetch_with_cursor(cursor, approval_id)

        record = _require_record(row)
        if record.status is ApprovalStatus.EXECUTED:
            return record
        raise ApprovalConflictError(
            f"Approval in {record.status.value} state cannot be marked executed"
        )

    async def mark_failed(self, approval_id: UUID, error_summary: str) -> ApprovalRecord:
        """Record a credential-redacted failure for an executing action."""

        safe_error = _safe_error_summary(error_summary)
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    UPDATE langgraph_approvals
                    SET status = 'failed',
                        error = %s,
                        updated_at = NOW()
                    WHERE approval_id = %s AND status = 'executing'
                    RETURNING *
                    """,
                    (safe_error, approval_id),
                )
                row = await cursor.fetchone()
                if row is None:
                    row = await self._fetch_with_cursor(cursor, approval_id)

        record = _require_record(row)
        if record.status is ApprovalStatus.FAILED:
            return record
        raise ApprovalConflictError(
            f"Approval in {record.status.value} state cannot be marked failed"
        )

    async def claim_expired(self, limit: int = 100) -> list[ApprovalRecord]:
        """Atomically claim expired pending approvals across concurrent workers."""

        limit = _positive_limit(limit)
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    WITH candidates AS (
                        SELECT approval_id
                        FROM langgraph_approvals
                        WHERE status = 'pending' AND expires_at <= NOW()
                        ORDER BY expires_at ASC, approval_id ASC
                        FOR UPDATE SKIP LOCKED
                        LIMIT %s
                    )
                    UPDATE langgraph_approvals AS approvals
                    SET status = 'expired',
                        decided_at = NOW(),
                        updated_at = NOW()
                    FROM candidates
                    WHERE approvals.approval_id = candidates.approval_id
                    RETURNING approvals.*
                    """,
                    (limit,),
                )
                rows = await cursor.fetchall()
        return [_to_record(row) for row in rows]

    @staticmethod
    async def _fetch_with_cursor(cursor, approval_id: UUID):
        await cursor.execute(
            "SELECT * FROM langgraph_approvals WHERE approval_id = %s",
            (approval_id,),
        )
        return await cursor.fetchone()


def _canonical_json(value: Any, *, label: str) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ValueError(f"Approval {label} must be JSON safe") from error


def _safe_error_summary(error_summary: str) -> str:
    summary = str(error_summary).replace("\x00", "")
    summary = _CREDENTIAL_ASSIGNMENT.sub(r"\1\2[REDACTED]", summary)
    summary = _AUTHORIZATION_VALUE.sub(r"\1[REDACTED]", summary)
    summary = _BEARER_VALUE.sub("Bearer [REDACTED]", summary)
    return summary[:1000]


def _validate_resume_payload(
    approval_id: UUID,
    resume_payload: ApprovalResumePayload,
) -> None:
    if resume_payload.approval_id != approval_id:
        raise ApprovalConflictError("Resume payload does not match the approval record")


def _positive_limit(limit: int) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("Approval query limit must be a positive integer")
    return limit


def _to_record(row: Any) -> ApprovalRecord:
    return ApprovalRecord.model_validate(row)


def _require_record(row: Any | None) -> ApprovalRecord:
    if row is None:
        raise ApprovalConflictError("Approval record was not found")
    return _to_record(row)
