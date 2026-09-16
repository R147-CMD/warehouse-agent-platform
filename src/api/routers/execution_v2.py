"""Authenticated approval and command status API for registered V2 actions."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.routers.chat_v2 import identity_from_current_user
from src.api.services.auth.dependencies import CurrentUser, get_current_user_context
from src.api.services.execution.control_plane import ControlledExecutionService
from src.api.services.feature_flags import FeatureFlags

router = APIRouter(prefix="/api/v2", tags=["Controlled Execution V2"])
_control_plane: ControlledExecutionService | None = None


def configure_execution_v2(control_plane: ControlledExecutionService) -> None:
    global _control_plane
    _control_plane = control_plane


def _service() -> ControlledExecutionService:
    if not FeatureFlags.from_env().execution_v2_enabled:
        raise HTTPException(503, "Execution V2 is disabled")
    if _control_plane is None:
        raise HTTPException(503, "Execution V2 is not configured")
    return _control_plane


class ApprovalDecisionRequestV2(BaseModel):
    approve: bool


@router.post("/actions/{action_id}/approval")
async def request_action_approval(
    action_id: str,
    current_user: CurrentUser = Depends(get_current_user_context),
):
    try:
        approval = await _service().request_approval(
            action_id, identity_from_current_user(current_user)
        )
        return approval.model_dump(mode="json")
    except (LookupError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


@router.post("/approvals/{approval_id}/decision")
async def decide_action_approval(
    approval_id: str,
    request: ApprovalDecisionRequestV2,
    current_user: CurrentUser = Depends(get_current_user_context),
):
    try:
        approval, command = await _service().decide(
            approval_id,
            identity_from_current_user(current_user),
            approve=request.approve,
        )
        return {
            "approval": approval.model_dump(mode="json"),
            "command": command.model_dump(mode="json") if command else None,
        }
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/commands/{command_id}")
async def get_command_status(
    command_id: str,
    current_user: CurrentUser = Depends(get_current_user_context),
):
    service = _service()
    command = await service.store.get_command(command_id)
    if command is None:
        raise HTTPException(404, "command not found")
    identity = identity_from_current_user(current_user)
    if command.tenant_id != identity.tenant_id:
        raise HTTPException(403, "cross-tenant command access is forbidden")
    return command.model_dump(mode="json")
