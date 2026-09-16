"""Service and MCP boundary tests for the four SAP EWM tools."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from src.adapters.wms.factory import WMSAdapterFactory
from src.adapters.wms.sap_ewm import SAPEWMAdapter
from src.adapters.wms.sap_ewm_config import SAPEWMConfig
from src.adapters.wms.sap_ewm_models import (
    SAPOrderTaskResult,
    SAPPage,
    SAPStockItem,
    SAPWarehouseOrder,
    SAPWriteResult,
)
from src.api.services.mcp.adapters.sap_ewm_adapter import (
    SAPEWMMCPAdapter,
    SAPEWMMCPAdapterConfig,
    get_sap_ewm_mcp_adapter,
)
from src.api.services.execution.models import Command
from src.api.services.mcp.adapters.wms_adapter import WMSAdapter, WMSConfig
from src.api.services.wms.integration_service import WMSIntegrationService


class ConcreteLegacyWMSAdapter(WMSAdapter):
    async def initialize(self) -> bool:
        return True

    async def health_check(self) -> dict[str, object]:
        return {"status": "unused"}


def sap_config() -> SAPEWMConfig:
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


def stock_page() -> SAPPage[SAPStockItem]:
    return SAPPage(
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


def order_result() -> SAPOrderTaskResult:
    return SAPOrderTaskResult(
        orders=[
            SAPWarehouseOrder(
                warehouse="EW01",
                order_id="2000005003",
                status="O",
                executing_resource="RES1",
                etag='W/"1"',
            )
        ]
    )


@pytest.mark.asyncio
async def test_service_delegates_only_to_a_sap_adapter() -> None:
    service = WMSIntegrationService()
    adapter = SAPEWMAdapter(sap_config(), client=AsyncMock())
    adapter.connected = True
    adapter.get_physical_stock = AsyncMock(return_value=stock_page())
    service.adapters["sap-ewm-default"] = adapter

    result = await service.get_physical_stock(
        "sap-ewm-default",
        product="TG11",
        storage_bin=None,
        limit=10,
        cursor=None,
        correlation_id="request-1",
    )

    assert result.items[0].sku == "TG11"
    adapter.get_physical_stock.assert_awaited_once_with(
        "TG11", None, 10, None, "request-1"
    )

    service.adapters["not-sap"] = AsyncMock()
    with pytest.raises(TypeError, match="not SAP EWM"):
        await service.get_physical_stock(
            "not-sap",
            product=None,
            storage_bin=None,
            limit=10,
            cursor=None,
            correlation_id="request-2",
        )


@pytest.mark.asyncio
async def test_stock_tool_delegates_with_one_request_id() -> None:
    service = AsyncMock(spec=WMSIntegrationService)
    service.adapters = {}
    service.add_wms_connection.return_value = True
    service.get_physical_stock.return_value = stock_page()
    adapter = SAPEWMMCPAdapter(
        config=SAPEWMMCPAdapterConfig(),
        sap_config=sap_config(),
        wms_service=service,
        request_id_factory=lambda: "request-1",
    )
    assert await adapter.initialize() is True

    result = await adapter.execute_tool(
        "sap_ewm_get_physical_stock", {"product": "TG11", "limit": 10}
    )

    service.get_physical_stock.assert_awaited_once_with(
        "sap-ewm-default",
        product="TG11",
        storage_bin=None,
        limit=10,
        cursor=None,
        correlation_id="request-1",
    )
    assert result["source_system"] == "sap_ewm"
    assert result["request_id"] == "request-1"
    assert result["data"]["items"][0]["quantity"] == "956"
    assert "base_url" not in result
    assert "password" not in result


@pytest.mark.asyncio
async def test_agent_facing_adapter_exposes_only_read_tools() -> None:
    service = AsyncMock(spec=WMSIntegrationService)
    service.adapters = {}
    service.add_wms_connection.return_value = True
    adapter = SAPEWMMCPAdapter(SAPEWMMCPAdapterConfig(), sap_config(), service)

    assert await adapter.initialize() is True
    assert set(adapter.tools) == {
        "sap_ewm_get_physical_stock",
        "sap_ewm_list_orders_and_tasks",
    }
    assert adapter.tools["sap_ewm_get_physical_stock"].metadata == {
        "read_only": True,
        "mutating": False,
        "requires_approval": False,
    }
    with pytest.raises(ValueError, match="not found"):
        await adapter.execute_tool(
            "sap_ewm_assign_warehouse_order",
            {
                "warehouse_order": "2000005003",
                "resource": "RES2",
                "reason": "balance workload",
            },
        )


@pytest.mark.asyncio
async def test_order_tool_serializes_domain_result() -> None:
    service = AsyncMock(spec=WMSIntegrationService)
    service.adapters = {}
    service.add_wms_connection.return_value = True
    service.list_orders_and_tasks.return_value = order_result()
    adapter = SAPEWMMCPAdapter(
        SAPEWMMCPAdapterConfig(),
        sap_config(),
        service,
        request_id_factory=lambda: "request-orders",
    )
    await adapter.initialize()

    result = await adapter.execute_tool(
        "sap_ewm_list_orders_and_tasks",
        {"order_id": "2000005003", "task_status": "O"},
    )

    assert result["data"]["orders"][0]["order_id"] == "2000005003"
    service.list_orders_and_tasks.assert_awaited_once_with(
        "sap-ewm-default",
        order_id="2000005003",
        task_status="O",
        resource=None,
        limit=50,
        cursor=None,
        correlation_id="request-orders",
    )


@pytest.mark.asyncio
async def test_wms_service_executes_and_reads_back_an_approved_command() -> None:
    now = datetime.now(UTC)
    command = Command(
        command_id="command-1",
        tenant_id="tenant-1",
        capability="sap.ewm.order.assign",
        action_id="action-1",
        action_hash="a" * 64,
        idempotency_key="tenant-1:assign:2000005003:RES2",
        target={
            "resource_type": "warehouse_order",
            "resource_id": "2000005003",
            "warehouse_id": "EW01",
            "expected_version": 'W/"APPROVED-1"',
        },
        arguments={"warehouse_order": "2000005003", "resource": "RES2"},
        expected_version='W/"APPROVED-1"',
        created_at=now,
        updated_at=now,
    )
    service = WMSIntegrationService()
    adapter = SAPEWMAdapter(sap_config(), client=AsyncMock())
    adapter.connected = True
    adapter.assign_warehouse_order = AsyncMock(
        return_value=SAPWriteResult(
            operation="assign_warehouse_order",
            entity_id="2000005003",
            status="ASSIGNED",
        )
    )
    adapter.get_warehouse_order = AsyncMock(
        return_value=order_result()
        .orders[0]
        .model_copy(update={"executing_resource": "RES2"})
    )
    service.adapters["sap-ewm-default"] = adapter

    submitted = await service.execute(command, connection_id="sap-ewm-default")
    verified = await service.read_back(command, connection_id="sap-ewm-default")

    assert submitted.accepted is True
    assert verified.verified is True
    assert verified.data["executing_resource"] == "RES2"
    adapter.assign_warehouse_order.assert_awaited_once_with(
        "2000005003",
        "RES2",
        correlation_id="command-1",
        expected_etag='W/"APPROVED-1"',
    )


@pytest.mark.asyncio
async def test_tool_schema_forbids_unknown_connection_or_credentials() -> None:
    service = AsyncMock(spec=WMSIntegrationService)
    service.adapters = {}
    service.add_wms_connection.return_value = True
    adapter = SAPEWMMCPAdapter(SAPEWMMCPAdapterConfig(), sap_config(), service)
    await adapter.initialize()

    schema = adapter.tools["sap_ewm_get_physical_stock"].parameters
    assert schema["additionalProperties"] is False
    assert "base_url" not in schema["properties"]
    assert "connection_id" not in schema["properties"]

    with pytest.raises(ValidationError):
        await adapter.execute_tool(
            "sap_ewm_get_physical_stock",
            {"product": "TG11", "base_url": "https://evil.example"},
        )


def test_factory_accepts_validated_sap_config() -> None:
    adapter = WMSAdapterFactory.create_adapter("sap_ewm", sap_config())

    assert isinstance(adapter, SAPEWMAdapter)
    assert adapter.sap_config is not None
    assert adapter.sap_config.warehouse == "EW01"


@pytest.mark.asyncio
async def test_disabled_singleton_needs_no_other_sap_environment(
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAP_EWM_ENABLED", "false")
    for name in (
        "SAP_EWM_BASE_URL",
        "SAP_EWM_WAREHOUSE",
        "SAP_EWM_USERNAME",
        "SAP_EWM_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)

    assert await get_sap_ewm_mcp_adapter() is None


@pytest.mark.asyncio
async def test_legacy_sap_wms_handler_does_not_fabricate_item001() -> None:
    legacy = ConcreteLegacyWMSAdapter(WMSConfig(wms_type="sap_ewm"))

    result = await legacy._get_inventory_levels()

    assert result["success"] is False
    assert "ITEM001" not in str(result)
