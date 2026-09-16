"""Authenticated API endpoints for agent run tracking."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status

from src.api.services.auth.dependencies import CurrentUser, get_current_user_context
from src.api.services.auth.models import UserRole
from src.api.services.runs import (
    TERMINAL_STATUSES,
    RunCancelRequest,
    RunDetailResponse,
    RunEventResponse,
    RunEventType,
    RunListFilters,
    RunListResponse,
    RunRecord,
    RunRetryRequest,
    RunStatus,
    RunType,
    get_run_manager,
)


router = APIRouter(prefix="/api/v1", tags=["Agent Runs"])


def _can_view_all(current_user: CurrentUser) -> bool:
    return current_user.user.role in {UserRole.ADMIN, UserRole.MANAGER}


def _can_manage_run(current_user: CurrentUser, run: RunRecord) -> bool:
    return _can_view_all(current_user) or run.user_id == current_user.user.id


@router.get("/runs", response_model=RunListResponse)
async def list_runs(
    run_status: RunStatus | None = Query(default=None, alias="status"),
    run_type: RunType | None = None,
    user_id: int | None = None,
    date_from: datetime | None = Query(default=None, alias="from"),
    date_to: datetime | None = Query(default=None, alias="to"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user_context),
) -> RunListResponse:
    """List runs visible to the current user."""

    filters = RunListFilters(
        status=run_status,
        run_type=run_type,
        user_id=user_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    items, total = await get_run_manager().repository.list_runs(
        filters,
        requesting_user_id=current_user.user.id,
        can_view_all=_can_view_all(current_user),
    )
    return RunListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/runs/{run_id}", response_model=RunDetailResponse)
async def get_run(
    run_id: UUID,
    current_user: CurrentUser = Depends(get_current_user_context),
) -> RunDetailResponse:
    """Return one run and its event timeline."""

    run = await _load_visible_run(run_id, current_user)
    return await _detail_response(run)


@router.get("/runs/{run_id}/events", response_model=list[RunEventResponse])
async def get_run_events(
    run_id: UUID,
    current_user: CurrentUser = Depends(get_current_user_context),
) -> list[RunEventResponse]:
    """Return one run's timeline events."""

    run = await _load_visible_run(run_id, current_user)
    events = await get_run_manager().repository.list_events(run.run_id)
    return [RunEventResponse.model_validate(event.model_dump()) for event in events]


@router.post("/runs/{run_id}/cancel", response_model=RunDetailResponse)
async def cancel_run(
    run_id: UUID,
    request: RunCancelRequest,
    current_user: CurrentUser = Depends(get_current_user_context),
) -> RunDetailResponse:
    """Request cooperative cancellation for one run."""

    run = await _load_visible_run(run_id, current_user)
    if not _can_manage_run(current_user, run):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="You cannot cancel this run",
        )
    if run.status in TERMINAL_STATUSES:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="Run is already terminal",
        )

    updated = await get_run_manager().request_cancel(run_id, request.reason)
    return await _detail_response(updated)


@router.post("/runs/{run_id}/retry", response_model=RunDetailResponse)
async def retry_run(
    run_id: UUID,
    request: RunRetryRequest,
    current_user: CurrentUser = Depends(get_current_user_context),
) -> RunDetailResponse:
    """Create a retry attempt for a failed run."""

    run = await _load_visible_run(run_id, current_user)
    if not _can_manage_run(current_user, run):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="You cannot retry this run",
        )
    if run.status is not RunStatus.FAILED:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="Only failed runs can be retried",
        )

    manager = get_run_manager()
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
        payload={
            "retry_of_run_id": str(run.run_id),
            "reason": request.reason,
        },
    )
    return await _detail_response(retry)


async def _load_visible_run(
    run_id: UUID,
    current_user: CurrentUser,
) -> RunRecord:
    run = await get_run_manager().repository.get_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Run not found",
        )
    if not _can_view_all(current_user) and run.user_id != current_user.user.id:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Run is not visible to this user",
        )
    return run


async def _detail_response(run: RunRecord) -> RunDetailResponse:
    events = await get_run_manager().repository.list_events(run.run_id)
    return RunDetailResponse(
        **run.model_dump(),
        events=[RunEventResponse.model_validate(event.model_dump()) for event in events],
    )
