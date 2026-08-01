"""Approval-boundary integration tests for discovered SAP EWM MCP tools."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.adapters.wms.sap_ewm_config import SAPEWMConfig
from src.adapters.wms.sap_ewm_models import SAPPage, SAPStockItem, SAPWriteResult
from src.api.services.approval import (
    ApprovalDecision,
    ApprovalExecutionContext,
    ApprovalGateway,
    ApprovalRecord,
    ApprovalRejectedError,
    ApprovalResumePayload,
    ApprovalStatus,
    bind_approval_context,
)
from src.api.services.mcp.adapters.sap_ewm_adapter import (
    SAPEWMMCPAdapter,
    SAPEWMMCPAdapterConfig,
)
from src.api.services.mcp.tool_discovery import ToolDiscoveryService
from src.api.services.wms.integration_service import WMSIntegrationService


class InMemoryApprovalRepository:
    """Small replay-safe repository double for the approval integration boundary."""

    def __init__(self) -> None:
        self.records: dict[str, ApprovalRecord] = {}

    async def ensure_pending(
        self, context, tool_key, tool_name, arguments, action_index, risk
    ) -> ApprovalRecord:
        action_key = f"{context.request_id}:{action_index}:{tool_key}"
        if action_key in self.records:
            return self.records[action_key]
        now = datetime.now(timezone.utc)
        record = ApprovalRecord(
            approval_id=uuid4(),
            thread_id=context.thread_id,
            checkpoint_ns=context.checkpoint_ns,
            request_id=context.request_id,
            action_key=action_key,
            idempotency_key=action_key,
            tool_key=tool_key,
            tool_name=tool_name,
            arguments=arguments,
            risk_level=risk.risk_level,
            risk_reasons=list(risk.reasons),
            requester_id=context.requester_id,
            requester_username=context.requester_username,
            status=ApprovalStatus.PENDING,
            created_at=now,
            expires_at=now + timedelta(hours=24),
            updated_at=now,
        )
        self.records[action_key] = record
        return record

    async def record_rejection(
        self, approval_id, resume_payload, *, expired=False
    ) -> ApprovalRecord:
        record = self._find(approval_id)
        updated = record.model_copy(
            update={
                "status": (
                    ApprovalStatus.EXPIRED if expired else ApprovalStatus.REJECTED
                ),
                "approver_id": resume_payload.approver_id,
                "approver_username": resume_payload.approver_username,
            }
        )
        self.records[record.action_key] = updated
        return updated

    async def claim_approved_execution(
        self, approval_id, resume_payload
    ) -> ApprovalRecord:
        record = self._find(approval_id)
        if record.status is ApprovalStatus.EXECUTED:
            return record
        updated = record.model_copy(
            update={
                "status": ApprovalStatus.EXECUTING,
                "approver_id": resume_payload.approver_id,
                "approver_username": resume_payload.approver_username,
            }
        )
        self.records[record.action_key] = updated
        return updated

    async def mark_executed(self, approval_id, result) -> ApprovalRecord:
        record = self._find(approval_id)
        updated = record.model_copy(
            update={"status": ApprovalStatus.EXECUTED, "result": result}
        )
        self.records[record.action_key] = updated
        return updated

    async def mark_failed(self, approval_id, error_summary) -> ApprovalRecord:
        record = self._find(approval_id)
        updated = record.model_copy(
            update={"status": ApprovalStatus.FAILED, "error": error_summary}
        )
        self.records[record.action_key] = updated
        return updated

    def _find(self, approval_id) -> ApprovalRecord:
        return next(
            record
            for record in self.records.values()
            if record.approval_id == approval_id
        )


def _sap_config() -> SAPEWMConfig:
    return SAPEWMConfig(
        enabled=True,
        mock_mode=True,
        base_url="http://sap.example.test",
        warehouse="EW01",
        client="100",
        auth_mode="basic",
        username="svc-user",
        password="svc-password",
        verify_tls=False,
    )


def _context(request_id: str) -> ApprovalExecutionContext:
    return ApprovalExecutionContext(
        thread_id="thread-sap",
        checkpoint_ns="operations",
        request_id=request_id,
        requester_id=7,
        requester_username="warehouse-user",
    )


@pytest.mark.asyncio
async def test_sap_read_write_approval_and_replay_boundary(monkeypatch) -> None:
    import src.api.services.approval.gateway as gateway_module
    import src.api.services.mcp.tool_discovery as discovery_module

    service = AsyncMock(spec=WMSIntegrationService)
    service.adapters = {}
    service.add_wms_connection.return_value = True
    service.get_physical_stock.return_value = SAPPage(
        items=[
            SAPStockItem(
                warehouse="EW01",
                sku="TG11",
                storage_bin="T010-02-05-A",
                quantity=Decimal("956"),
                unit="EA",
                stock_item_uuid="stock-uuid-1",
            )
        ]
    )
    service.assign_warehouse_order.return_value = SAPWriteResult(
        operation="assign_warehouse_order",
        entity_id="2000005003",
        status="ASSIGNED",
    )
    adapter = SAPEWMMCPAdapter(
        SAPEWMMCPAdapterConfig(),
        _sap_config(),
        service,
        request_id_factory=lambda: "sap-request-id",
    )
    await adapter.initialize()

    discovery = ToolDiscoveryService()
    assert await discovery.register_discovery_source(
        "sap_ewm_tools", adapter, "mcp_adapter"
    )
    tools = {
        tool.name: tool.tool_id
        for tool in await discovery.get_tools_by_source("sap_ewm_tools")
    }

    repository = InMemoryApprovalRepository()
    gateway = ApprovalGateway(repository_provider=lambda: repository)
    monkeypatch.setattr(discovery_module, "get_approval_gateway", lambda: gateway)
    decision = {"value": ApprovalDecision.APPROVE}

    def resume_approval(payload: dict[str, object]) -> dict[str, object]:
        return ApprovalResumePayload(
            approval_id=payload["approval_id"],
            decision=decision["value"],
            approver_id=11,
            approver_username="shift-manager",
            reason="verified",
        ).model_dump(mode="json")

    monkeypatch.setattr(gateway_module, "interrupt", resume_approval)

    stock = await discovery.execute_tool(
        tools["sap_ewm_get_physical_stock"],
        {"product": "TG11"},
    )
    assert stock["data"]["items"][0]["sku"] == "TG11"
    service.get_physical_stock.assert_awaited_once()
    assert repository.records == {}

    write_arguments = {
        "warehouse_order": "2000005003",
        "resource": "RES2",
        "reason": "balance workload",
    }
    decision["value"] = ApprovalDecision.REJECT
    with bind_approval_context(_context("request-reject")):
        with pytest.raises(ApprovalRejectedError):
            await discovery.execute_tool(
                tools["sap_ewm_assign_warehouse_order"],
                write_arguments,
                action_index=0,
            )
    service.assign_warehouse_order.assert_not_awaited()

    decision["value"] = ApprovalDecision.APPROVE
    approval_context = _context("request-approve")
    with bind_approval_context(approval_context):
        first = await discovery.execute_tool(
            tools["sap_ewm_assign_warehouse_order"],
            write_arguments,
            action_index=0,
        )
    with bind_approval_context(approval_context):
        replay = await discovery.execute_tool(
            tools["sap_ewm_assign_warehouse_order"],
            write_arguments,
            action_index=0,
        )

    assert first["data"]["status"] == "ASSIGNED"
    assert replay == first
    service.assign_warehouse_order.assert_awaited_once()
