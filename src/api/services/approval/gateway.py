"""Replay-safe approval boundary for high-risk tool execution."""

import json
import math
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from typing import Any
from uuid import UUID

from langgraph.types import interrupt

from src.api.services.runs import (
    RunEventSeverity,
    RunEventType,
    get_run_manager,
)

from .context import get_approval_context
from .manager import ApprovalManager, get_approval_manager
from .models import (
    ApprovalConflictError,
    ApprovalDecision,
    ApprovalRejectedError,
    ApprovalResumePayload,
    ApprovalStatus,
)
from .policy import ApprovalPolicy, ToolDescriptor
from .repository import ApprovalRepository


_CONNECTION_URL = re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s]+")
_CREDENTIAL = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|access[_-]?key)\b"
    r"(\s*[:=]\s*)([^\s,;&]+)"
)
_AUTHORIZATION = re.compile(
    r"(?i)\b(authorization\s*[:=]\s*)(?:bearer|basic)?\s*[^\s,;&]+"
)
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_FALLBACK_RESULT_LIMIT = 2000


class ApprovalGateway:
    """Require durable human approval before a risky tool can execute."""

    def __init__(
        self,
        *,
        approval_manager: ApprovalManager | None = None,
        repository_provider: Callable[[], ApprovalRepository] | None = None,
        policy: ApprovalPolicy | None = None,
    ) -> None:
        self._approval_manager = approval_manager
        self._repository_provider = repository_provider
        self._policy = policy or ApprovalPolicy()

    def requires_approval(self, tool: ToolDescriptor) -> bool:
        """Apply the gateway's risk policy without executing the tool."""

        return self._policy.requires_approval(tool)

    async def execute(
        self,
        *,
        tool_key: str,
        tool: Any,
        arguments: dict[str, Any],
        action_index: int,
        executor: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Execute a tool directly or behind a replay-safe approval interrupt."""

        risk = self._policy.assess(tool)
        if not risk.requires_approval:
            return await executor()

        context = get_approval_context()
        if context is None:
            raise ApprovalConflictError(
                "Approval context is unavailable; the action was not executed."
            )

        repository = self._get_repository()
        record = await repository.ensure_pending(
            context,
            tool_key,
            tool.name,
            arguments,
            action_index,
            risk,
        )
        if record.run_id is not None:
            try:
                run_manager = get_run_manager()
                await run_manager.mark_waiting_approval(
                    record.run_id,
                    record.approval_id,
                )
                await run_manager.emit_event(
                    run_id=record.run_id,
                    event_type=RunEventType.APPROVAL_REQUESTED,
                    message=f"需要审批：{record.tool_name}",
                    tool_name=record.tool_name,
                    approval_id=record.approval_id,
                    payload={
                        "action": record.action_key,
                        "risk_level": record.risk_level,
                        "risk_reasons": record.risk_reasons,
                    },
                )
            except Exception as error:
                raise ApprovalConflictError(
                    "Run event persistence failed; the action was not executed."
                ) from error

        resume_value = interrupt(
            record.to_interrupt_payload().model_dump(mode="json")
        )
        resume_payload = ApprovalResumePayload.model_validate(resume_value)
        if resume_payload.approval_id != record.approval_id:
            raise ApprovalConflictError(
                "Resume payload does not match the approval record"
            )

        if resume_payload.decision is ApprovalDecision.REJECT:
            rejected = await repository.record_rejection(
                record.approval_id,
                resume_payload,
                expired=(
                    resume_payload.approver_username.strip().lower()
                    == "system-expiry"
                ),
            )
            await _emit_approval_decision_event(rejected)
            raise ApprovalRejectedError()

        if record.status is ApprovalStatus.EXECUTED:
            return record.result

        claimed = await repository.claim_approved_execution(
            record.approval_id,
            resume_payload,
        )
        await _emit_approval_decision_event(claimed)
        if claimed.status is ApprovalStatus.EXECUTED:
            return claimed.result
        if claimed.status is not ApprovalStatus.EXECUTING:
            raise ApprovalConflictError(
                "Approval could not be claimed for execution"
            )

        try:
            await _emit_tool_event(
                claimed,
                RunEventType.TOOL_STARTED,
                "已批准，开始执行工具",
            )
            result = await executor()
        except Exception as error:
            try:
                failed_record = await repository.mark_failed(
                    record.approval_id,
                    _safe_error_summary(error),
                )
                await _emit_tool_event(
                    failed_record,
                    RunEventType.RUN_FAILED,
                    "工具执行失败",
                    severity=RunEventSeverity.ERROR,
                    payload={"error": _safe_error_summary(error)},
                )
                if failed_record.run_id is not None:
                    await get_run_manager().mark_failed(
                        failed_record.run_id,
                        error,
                        error_code=type(error).__name__,
                    )
            except Exception:
                # Preserve the original tool failure for the caller.
                pass
            raise

        executed = await repository.mark_executed(
            record.approval_id,
            _normalize_result(result),
        )
        await _emit_tool_event(
            executed,
            RunEventType.TOOL_COMPLETED,
            "工具执行完成",
            payload={"result": executed.result},
        )
        return result

    def _get_repository(self) -> ApprovalRepository:
        if self._repository_provider is not None:
            return self._repository_provider()

        manager = self._approval_manager or get_approval_manager()
        return manager.repository


def _normalize_result(value: Any, *, _seen: set[int] | None = None) -> Any:
    """Convert tool output to JSON-safe values without changing caller output."""

    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else _bounded_repr(value)
    if isinstance(value, Enum):
        return _normalize_result(value.value, _seen=_seen)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")[:_FALLBACK_RESULT_LIMIT]

    seen = _seen if _seen is not None else set()
    identity = id(value)
    if identity in seen:
        return _bounded_repr(value)
    seen.add(identity)
    try:
        if isinstance(value, Mapping):
            return {
                str(key): _normalize_result(item, _seen=seen)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple, set, frozenset)):
            return [_normalize_result(item, _seen=seen) for item in value]

        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            return _normalize_result(model_dump(mode="json"), _seen=seen)
        if is_dataclass(value) and not isinstance(value, type):
            return _normalize_result(asdict(value), _seen=seen)

        json.dumps(value, ensure_ascii=False, allow_nan=False)
        return value
    except Exception:
        return _bounded_repr(value)
    finally:
        seen.discard(identity)


def _bounded_repr(value: Any) -> str:
    try:
        rendered = repr(value)
    except Exception:
        rendered = f"<{type(value).__name__}>"
    return rendered[:_FALLBACK_RESULT_LIMIT]


def _safe_error_summary(error: Exception) -> str:
    summary = f"{type(error).__name__}: {error}".replace("\x00", "")
    summary = _CONNECTION_URL.sub("[REDACTED URL]", summary)
    summary = _CREDENTIAL.sub(r"\1\2[REDACTED]", summary)
    summary = _AUTHORIZATION.sub(r"\1[REDACTED]", summary)
    summary = _BEARER.sub("Bearer [REDACTED]", summary)
    return summary[:1000]


_approval_gateway: ApprovalGateway | None = None


def get_approval_gateway() -> ApprovalGateway:
    """Return the process-wide approval gateway."""

    global _approval_gateway
    if _approval_gateway is None:
        _approval_gateway = ApprovalGateway()
    return _approval_gateway


async def _emit_approval_decision_event(record) -> None:
    if record.run_id is None:
        return
    if record.status is ApprovalStatus.REJECTED:
        event_type = RunEventType.APPROVAL_REJECTED
        message = "审批已拒绝"
        severity = RunEventSeverity.WARNING
    elif record.status is ApprovalStatus.EXPIRED:
        event_type = RunEventType.APPROVAL_EXPIRED
        message = "审批已过期"
        severity = RunEventSeverity.WARNING
    else:
        event_type = RunEventType.APPROVAL_APPROVED
        message = "审批已通过"
        severity = RunEventSeverity.INFO
    await get_run_manager().emit_event(
        run_id=record.run_id,
        event_type=event_type,
        severity=severity,
        message=message,
        tool_name=record.tool_name,
        approval_id=record.approval_id,
        payload={"status": record.status.value, "action": record.action_key},
    )


async def _emit_tool_event(
    record,
    event_type: RunEventType,
    message: str,
    *,
    severity: RunEventSeverity = RunEventSeverity.INFO,
    payload: dict[str, Any] | None = None,
) -> None:
    if record.run_id is None:
        return
    await get_run_manager().emit_event(
        run_id=record.run_id,
        event_type=event_type,
        severity=severity,
        message=message,
        tool_name=record.tool_name,
        approval_id=record.approval_id,
        payload=payload or {"action": record.action_key},
    )
