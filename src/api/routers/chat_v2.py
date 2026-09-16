"""Feature-gated V2 chat endpoint; legacy chat remains the default rollback path."""

from __future__ import annotations

import os
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.api.domain.identity import IdentityContext
from src.api.services.auth.dependencies import CurrentUser, get_current_user_context
from src.api.services.feature_flags import FeatureFlags
from src.api.services.runtime_v2 import WarehouseAgentPlatformV2

router = APIRouter(prefix="/api/v2", tags=["Agent Runtime V2"])


class ChatRequestV2(BaseModel):
    message: str = Field(min_length=1, max_length=8_000)
    conversation_id: str = Field(min_length=1, max_length=256)
    context: dict = Field(default_factory=dict)
    require_evidence: bool = True


_platform: WarehouseAgentPlatformV2 | None = None


def configure_platform_v2(platform: WarehouseAgentPlatformV2) -> None:
    """Application composition hook for real Retrieval/MCP/domain providers."""

    global _platform
    _platform = platform


def identity_from_current_user(current_user: CurrentUser) -> IdentityContext:
    permission_scopes = {
        permission.value.replace(":", ".") for permission in current_user.permissions
    }
    scopes = set(permission_scopes)
    if "operations.write" in scopes or "operations.assign" in scopes:
        scopes.add("operations.propose")
    if "reports.view" in scopes:
        scopes.update({"document.read", "forecast.read"})
    if "system.admin" in scopes:
        scopes.update(
            {
                "document.read",
                "document.write",
                "equipment.read",
                "equipment.dispatch",
                "sap.order.assign",
                "sap.task.confirm",
            }
        )
    warehouses = tuple(
        item.strip()
        for item in os.getenv("WAREHOUSE_SCOPE", "WH-01").split(",")
        if item.strip()
    )
    return IdentityContext(
        tenant_id=os.getenv("WAREHOUSE_TENANT_ID", "default"),
        user_id=str(current_user.user.id),
        username=current_user.user.username,
        roles=(current_user.user.role.value,),
        scopes=tuple(sorted(scopes)),
        warehouse_scope=warehouses,
        authenticated_at=datetime.now(UTC),
    )


@router.post("/chat")
async def chat_v2(
    request: ChatRequestV2,
    current_user: CurrentUser = Depends(get_current_user_context),
):
    if not FeatureFlags.from_env().agent_runtime_v2_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent runtime V2 is disabled; use /api/v1/chat.",
        )
    if _platform is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent runtime V2 providers are not configured.",
        )
    result = await _platform.process(
        request.message,
        identity_from_current_user(current_user),
        conversation_id=request.conversation_id,
        require_evidence=request.require_evidence,
        context=request.context,
    )
    return {
        "run": result["run"].model_dump(mode="json"),
        "status": result["status"],
        "planning_mode": result["planning_mode"],
        "answer": result["final_answer"],
        "evidence": [
            item.model_dump(mode="json") for item in result.get("evidence_refs", [])
        ],
        "proposed_actions": [
            item.model_dump(mode="json") for item in result.get("proposed_actions", [])
        ],
    }
