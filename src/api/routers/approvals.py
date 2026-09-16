"""Authenticated API endpoints for durable human approval workflows."""

import re
import math
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.api.graphs.mcp_integrated_planner_graph import (
    get_mcp_planner_graph,
    resume_expired_approval,
)
from src.api.services.approval import (
    ApprovalConflictError,
    ApprovalDecision,
    ApprovalRecord,
    ApprovalResumePayload,
    ApprovalStatus,
    get_approval_manager,
)
from src.api.services.auth.dependencies import CurrentUser, get_current_user_context
from src.api.services.auth.models import UserRole
from src.api.services.runs import get_run_manager


router = APIRouter(prefix="/api/v1", tags=["Human Approvals"])

_SENSITIVE_KEY = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|access[_-]?key|"
    r"authorization|cookie|credential)"
)
_CONNECTION_URL = re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s\"'<>]+")
_CREDENTIAL_VALUE = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|access[_-]?key)\b"
    r"(\s*[:=]\s*)([^\s,;&]+)"
)
_AUTHORIZATION_VALUE = re.compile(
    r"(?i)\b(authorization\s*[:=]\s*)(?:bearer|basic)?\s*[^\s,;&]+"
)
_BEARER_VALUE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_MAX_SAFE_TEXT = 2000


class ApprovalDecisionRequest(BaseModel):
    """A manager or administrator's decision for a pending action."""

    decision: ApprovalDecision
    reason: str | None = Field(default=None, max_length=500)


class ApprovalResponse(BaseModel):
    """Credential-safe approval data exposed to authorized clients."""

    approval_id: UUID
    run_id: UUID | None = None
    action: str
    tool_name: str
    arguments: dict[str, Any]
    risk_level: str
    risk_reasons: list[str]
    requester: str
    approver: str | None = None
    status: ApprovalStatus
    created_at: datetime
    expires_at: datetime
    decided_at: datetime | None = None
    executed_at: datetime | None = None
    result: Any | None = None
    error: str | None = None


class ApprovalWorkflowResponse(BaseModel):
    """Safe status returned by a resumed Planner workflow."""

    response: str
    route: str
    intent: str
    session_id: str
    execution_status: str = "completed"
    pending_approvals: list[dict[str, Any]] | None = None
    confidence: float | None = None
    context: dict[str, Any] | None = None
    structured_data: Any | None = None
    recommendations: list[str] | None = None
    actions_taken: list[dict[str, Any]] | None = None
    reasoning_chain: dict[str, Any] | None = None
    reasoning_steps: list[dict[str, Any]] | None = None


class ApprovalDecisionResponse(BaseModel):
    """The durable record and any workflow result produced by a decision."""

    approval: ApprovalResponse
    workflow: ApprovalWorkflowResponse | None = None


async def require_approval_role(
    current_user: CurrentUser = Depends(get_current_user_context),
) -> CurrentUser:
    """Allow approval access only to server-authenticated privileged roles."""

    if current_user.user.role not in {UserRole.MANAGER, UserRole.ADMIN}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager or administrator role required",
        )
    return current_user


def sanitize_pending_approvals(payloads: Any) -> list[dict[str, Any]]:
    """Return only safe fields from Planner approval interrupt payloads."""

    if not isinstance(payloads, list):
        return []

    safe_payloads: list[dict[str, Any]] = []
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        safe_payloads.append(
            {
                "approval_id": _safe_text(payload.get("approval_id")),
                "run_id": _safe_text(payload.get("run_id")),
                "action": _safe_text(payload.get("action")),
                "tool_name": _safe_text(payload.get("tool_name")),
                "arguments": _sanitize_json(payload.get("arguments", {})),
                "risk_level": _safe_text(payload.get("risk_level")),
                "risk_reasons": [
                    _safe_text(reason)
                    for reason in payload.get("risk_reasons", [])
                    if isinstance(reason, (str, int, float, bool))
                ],
                "requester_username": _safe_text(
                    payload.get("requester_username")
                ),
                "created_at": payload.get("created_at"),
                "expires_at": payload.get("expires_at"),
            }
        )
    return safe_payloads


@router.get("/chat/approvals/pending", response_model=list[ApprovalResponse])
async def list_pending_approvals(
    current_user: CurrentUser = Depends(require_approval_role),
) -> list[ApprovalResponse]:
    """List pending approvals visible to an authorized approver."""

    del current_user
    try:
        records = await get_approval_manager().repository.list_pending()
        visible_records: list[ApprovalResponse] = []
        for record in records:
            if await _resume_if_expired(record):
                continue
            visible_records.append(_approval_response(record))
        return visible_records
    except HTTPException:
        raise
    except Exception as exc:
        raise _internal_error(exc) from exc


@router.get("/chat/approvals/{approval_id}", response_model=ApprovalResponse)
async def get_approval(
    approval_id: UUID,
    current_user: CurrentUser = Depends(require_approval_role),
) -> ApprovalResponse:
    """Return one credential-safe approval record."""

    del current_user
    try:
        record = await _load_approval(approval_id)
        if await _resume_if_expired(record):
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Approval has expired",
            )
        return _approval_response(record)
    except HTTPException:
        raise
    except Exception as exc:
        raise _internal_error(exc) from exc


@router.post(
    "/chat/approvals/{approval_id}/decision",
    response_model=ApprovalDecisionResponse,
    response_model_exclude_none=True,
)
async def decide_approval(
    approval_id: UUID,
    request: ApprovalDecisionRequest,
    current_user: CurrentUser = Depends(require_approval_role),
) -> ApprovalDecisionResponse:
    """Resume an interrupted Planner workflow with an authenticated decision."""

    try:
        manager = get_approval_manager()
        record = await _load_approval(approval_id)
        if await _resume_if_expired(record):
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Approval has expired",
            )

        existing_decision = _recorded_decision(record.status)
        if existing_decision is not None:
            if existing_decision is request.decision:
                return ApprovalDecisionResponse(
                    approval=_approval_response(record),
                    workflow=None,
                )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Approval already has a conflicting decision",
            )
        if record.status is not ApprovalStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Approval is not pending",
            )

        resume_payload = ApprovalResumePayload(
            approval_id=record.approval_id,
            decision=request.decision,
            approver_id=current_user.user.id,
            approver_username=current_user.user.username,
            reason=request.reason,
        )
        try:
            workflow = await (
                await get_mcp_planner_graph()
            ).resume_approval(record, resume_payload)
        except ApprovalConflictError as exc:
            current = await _load_approval(approval_id)
            current_decision = _recorded_decision(current.status)
            if current_decision is request.decision:
                return ApprovalDecisionResponse(
                    approval=_approval_response(current),
                    workflow=None,
                )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Approval state changed before the decision completed",
            ) from exc

        updated_record = await manager.repository.get(approval_id)
        if updated_record is None:
            raise RuntimeError("Approval record was unavailable after workflow resume")
        await _sync_run_after_workflow(updated_record, workflow)
        return ApprovalDecisionResponse(
            approval=_approval_response(updated_record),
            workflow=_workflow_response(workflow, updated_record.thread_id),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _internal_error(exc) from exc


async def _load_approval(approval_id: UUID) -> ApprovalRecord:
    record = await get_approval_manager().repository.get(approval_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval not found",
        )
    return record


async def _resume_if_expired(record: ApprovalRecord) -> bool:
    if record.status is not ApprovalStatus.PENDING:
        return False

    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at > datetime.now(timezone.utc):
        return False

    await resume_expired_approval(record)
    return True


def _recorded_decision(status_value: ApprovalStatus) -> ApprovalDecision | None:
    if status_value in {ApprovalStatus.REJECTED, ApprovalStatus.EXPIRED}:
        return ApprovalDecision.REJECT
    if status_value in {
        ApprovalStatus.APPROVED,
        ApprovalStatus.EXECUTING,
        ApprovalStatus.EXECUTED,
        ApprovalStatus.FAILED,
    }:
        return ApprovalDecision.APPROVE
    return None


def _approval_response(record: ApprovalRecord) -> ApprovalResponse:
    arguments = _sanitize_json(record.arguments)
    if not isinstance(arguments, dict):
        arguments = {}
    return ApprovalResponse(
        approval_id=record.approval_id,
        run_id=record.run_id,
        action=_safe_text(record.action_key),
        tool_name=_safe_text(record.tool_name),
        arguments=arguments,
        risk_level=_safe_text(record.risk_level),
        risk_reasons=[_safe_text(reason) for reason in record.risk_reasons],
        requester=_safe_text(record.requester_username),
        approver=(
            _safe_text(record.approver_username)
            if record.approver_username is not None
            else None
        ),
        status=record.status,
        created_at=record.created_at,
        expires_at=record.expires_at,
        decided_at=record.decided_at,
        executed_at=record.executed_at,
        result=_sanitize_json(record.result),
        error=_safe_text(record.error) if record.error is not None else None,
    )


def _workflow_response(
    workflow: Any,
    fallback_session_id: str,
) -> ApprovalWorkflowResponse:
    if not isinstance(workflow, dict):
        raise RuntimeError("Approval workflow returned an invalid response")
    execution_status = _safe_text(
        workflow.get("execution_status") or "completed"
    )
    minimal_response = {
        "response": _safe_text(
            workflow.get("response")
            or "The approval decision was recorded and the workflow continued."
        ),
        "route": _safe_text(workflow.get("route") or "unknown"),
        "intent": _safe_text(workflow.get("intent") or "unknown"),
        "session_id": _safe_text(
            workflow.get("session_id") or fallback_session_id
        ),
        "execution_status": execution_status,
        "pending_approvals": sanitize_pending_approvals(
            workflow.get("pending_approvals")
        ),
    }
    if execution_status == "approval_required":
        return ApprovalWorkflowResponse(**minimal_response)

    raw_context = workflow.get("context")
    context = raw_context if isinstance(raw_context, dict) else {}
    raw_structured_response = workflow.get("structured_response")
    structured_response = (
        raw_structured_response
        if isinstance(raw_structured_response, dict)
        else {}
    )

    confidence = workflow.get("confidence")
    if confidence is None:
        confidence = structured_response.get("confidence")

    recommendations = workflow.get("recommendations")
    if not isinstance(recommendations, list):
        recommendations = structured_response.get("recommendations")

    actions_taken = workflow.get("actions_taken")
    if not isinstance(actions_taken, list):
        actions_taken = structured_response.get("actions_taken")
    if not isinstance(actions_taken, list):
        actions_taken = context.get("actions_taken")

    reasoning_chain = workflow.get("reasoning_chain")
    if not isinstance(reasoning_chain, dict):
        reasoning_chain = context.get("reasoning_chain")
    reasoning_steps = workflow.get("reasoning_steps")
    if not isinstance(reasoning_steps, list):
        reasoning_steps = context.get("reasoning_steps")

    return ApprovalWorkflowResponse(
        **minimal_response,
        confidence=_safe_confidence(confidence),
        context=_safe_workflow_context(context),
        structured_data=_sanitize_json(structured_response.get("data")),
        recommendations=_safe_text_list(recommendations),
        actions_taken=_safe_dict_list(actions_taken),
        reasoning_chain=_safe_optional_dict(reasoning_chain),
        reasoning_steps=_safe_dict_list(reasoning_steps),
    )


async def _sync_run_after_workflow(
    record: ApprovalRecord,
    workflow: Any,
) -> None:
    """Best-effort run status sync after an approval resumes a graph."""

    if record.run_id is None or not isinstance(workflow, dict):
        return
    try:
        manager = get_run_manager()
        execution_status = str(workflow.get("execution_status") or "completed")
        if execution_status == "approval_required":
            await manager.mark_waiting_approval(record.run_id)
        elif execution_status == "cancelled":
            await manager.mark_cancelled(record.run_id, "审批恢复后任务取消")
        else:
            await manager.mark_completed(
                record.run_id,
                str(workflow.get("response") or "审批恢复后任务完成")[:200],
            )
    except Exception:
        return


def _safe_confidence(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    confidence = float(value)
    if not math.isfinite(confidence):
        return None
    return max(0.0, min(1.0, confidence))


def _safe_workflow_context(context: dict[str, Any]) -> dict[str, Any]:
    excluded = {
        "reasoning_chain",
        "reasoning_steps",
        "structured_response",
        "tool_execution_results",
        "mcp_results",
    }
    safe_context: dict[str, Any] = {}
    for raw_key, value in context.items():
        if raw_key in excluded or _SENSITIVE_KEY.search(str(raw_key)):
            continue
        if value is None or isinstance(value, (str, bool, int, float)):
            safe_context[_safe_text(raw_key, max_length=200)] = _sanitize_json(value)
        elif isinstance(value, list) and all(
            item is None or isinstance(item, (str, bool, int, float))
            for item in value
        ):
            safe_context[_safe_text(raw_key, max_length=200)] = _sanitize_json(value)
    return safe_context


def _safe_text_list(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    return [_safe_text(item) for item in value if isinstance(item, str)]


def _safe_dict_list(value: Any) -> list[dict[str, Any]] | None:
    if not isinstance(value, list):
        return None
    safe_items = [
        _sanitize_json(item)
        for item in value
        if isinstance(item, dict)
    ]
    return safe_items


def _safe_optional_dict(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    sanitized = _sanitize_json(value)
    return sanitized if isinstance(sanitized, dict) else None


def _sanitize_json(value: Any, *, depth: int = 0) -> Any:
    if depth > 8:
        return "[TRUNCATED]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _safe_text(value)
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = _safe_text(raw_key, max_length=200)
            sanitized[key] = (
                "[REDACTED]"
                if _SENSITIVE_KEY.search(str(raw_key))
                else _sanitize_json(item, depth=depth + 1)
            )
        return sanitized
    if isinstance(value, (list, tuple)):
        return [_sanitize_json(item, depth=depth + 1) for item in value]
    return _safe_text(value)


def _safe_text(value: Any, *, max_length: int = _MAX_SAFE_TEXT) -> str:
    text = str(value if value is not None else "").replace("\x00", "")
    text = _CONNECTION_URL.sub("[REDACTED URL]", text)
    text = _CREDENTIAL_VALUE.sub(r"\1\2[REDACTED]", text)
    text = _AUTHORIZATION_VALUE.sub(r"\1[REDACTED]", text)
    text = _BEARER_VALUE.sub("Bearer [REDACTED]", text)
    return text[:max_length]


def _internal_error(exc: Exception) -> HTTPException:
    # Deliberately omit exception text: it may contain credentials or connection URLs.
    del exc
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Approval request failed",
    )
