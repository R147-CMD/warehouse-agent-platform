"""MCP adapter exposing four stable SAP EWM business tools."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from src.adapters.wms.sap_ewm_config import SAPEWMConfig
from src.adapters.wms.sap_ewm_errors import SAPEWMError, SAPEWMErrorCode
from src.api.services.mcp.base import AdapterConfig, AdapterType, MCPAdapter
from src.api.services.mcp.client import MCPConnectionType
from src.api.services.mcp.server import MCPTool, MCPToolType
from src.api.services.wms.integration_service import (
    WMSIntegrationService,
    get_wms_service,
)


class _ToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class GetPhysicalStockArgs(_ToolArguments):
    product: str | None = Field(default=None, min_length=1)
    storage_bin: str | None = Field(default=None, min_length=1)
    limit: int = Field(default=50, ge=1, le=100)
    cursor: str | None = Field(default=None, min_length=1)


class ListOrdersAndTasksArgs(_ToolArguments):
    order_id: str | None = Field(default=None, min_length=1)
    task_status: str | None = Field(default=None, min_length=1)
    resource: str | None = Field(default=None, min_length=1)
    limit: int = Field(default=50, ge=1, le=100)
    cursor: str | None = Field(default=None, min_length=1)


class AssignWarehouseOrderArgs(_ToolArguments):
    warehouse_order: str = Field(min_length=1)
    resource: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class ConfirmWarehouseTaskArgs(_ToolArguments):
    warehouse_task: str = Field(min_length=1)
    warehouse_task_item: str = Field(default="0", min_length=1)
    reason: str = Field(min_length=1)


@dataclass
class SAPEWMMCPAdapterConfig(AdapterConfig):
    name: str = "sap_ewm_tools"
    adapter_type: AdapterType = AdapterType.WMS
    endpoint: str = "local://sap_ewm_tools"
    connection_type: MCPConnectionType = MCPConnectionType.STDIO


class SAPEWMMCPAdapter(MCPAdapter):
    """Validate Agent arguments and delegate to WMSIntegrationService."""

    def __init__(
        self,
        config: SAPEWMMCPAdapterConfig,
        sap_config: SAPEWMConfig,
        wms_service: WMSIntegrationService,
        request_id_factory: Callable[[], str] = lambda: str(uuid4()),
    ) -> None:
        super().__init__(config)
        self.sap_config = sap_config
        self.wms_service = wms_service
        self.request_id_factory = request_id_factory
        self._initialized = False

    async def initialize(self) -> bool:
        if self._initialized:
            return True
        if self.sap_config.connection_id not in self.wms_service.adapters:
            connected = await self.wms_service.add_wms_connection(
                "sap_ewm",
                self.sap_config,
                self.sap_config.connection_id,
            )
            if not connected:
                return False
        self._register_tools()
        self.connected = True
        self._initialized = True
        return True

    async def connect(self) -> bool:
        return await self.initialize()

    async def disconnect(self) -> bool:
        if self.sap_config.connection_id in self.wms_service.adapters:
            await self.wms_service.remove_wms_connection(self.sap_config.connection_id)
        self.connected = False
        self._initialized = False
        return True

    async def health_check(self) -> dict[str, Any]:
        return {
            "status": "healthy" if self.connected else "disconnected",
            "connected": self.connected,
            "connection_id": self.sap_config.connection_id,
            "warehouse": self.sap_config.warehouse,
            "tools_count": len(self.tools),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _register_tools(self) -> None:
        self.tools = {
            "sap_ewm_get_physical_stock": MCPTool(
                name="sap_ewm_get_physical_stock",
                description="Query authorized SAP EWM physical stock by product or storage bin",
                tool_type=MCPToolType.FUNCTION,
                parameters=GetPhysicalStockArgs.model_json_schema(),
                handler=self._get_physical_stock,
                metadata={
                    "read_only": True,
                    "mutating": False,
                    "requires_approval": False,
                },
            ),
            "sap_ewm_list_orders_and_tasks": MCPTool(
                name="sap_ewm_list_orders_and_tasks",
                description="Query authorized SAP EWM warehouse orders and tasks",
                tool_type=MCPToolType.FUNCTION,
                parameters=ListOrdersAndTasksArgs.model_json_schema(),
                handler=self._list_orders_and_tasks,
                metadata={
                    "read_only": True,
                    "mutating": False,
                    "requires_approval": False,
                },
            ),
        }
        if os.getenv("SAP_EWM_EXPOSE_LEGACY_WRITE_TOOLS", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            self.tools.update(
                {
                    "sap_ewm_assign_warehouse_order": MCPTool(
                        name="sap_ewm_assign_warehouse_order",
                        description=(
                            "Legacy: assign an SAP EWM warehouse order behind the "
                            "legacy approval gateway"
                        ),
                        tool_type=MCPToolType.FUNCTION,
                        parameters=AssignWarehouseOrderArgs.model_json_schema(),
                        handler=self._assign_warehouse_order,
                        metadata={
                            "read_only": False,
                            "mutating": True,
                            "requires_approval": True,
                            "legacy_only": True,
                        },
                    ),
                    "sap_ewm_confirm_warehouse_task": MCPTool(
                        name="sap_ewm_confirm_warehouse_task",
                        description=(
                            "Legacy: confirm an SAP EWM warehouse task behind the "
                            "legacy approval gateway"
                        ),
                        tool_type=MCPToolType.FUNCTION,
                        parameters=ConfirmWarehouseTaskArgs.model_json_schema(),
                        handler=self._confirm_warehouse_task,
                        metadata={
                            "read_only": False,
                            "mutating": True,
                            "requires_approval": True,
                            "legacy_only": True,
                        },
                    ),
                }
            )

    async def _get_physical_stock(self, arguments: dict[str, Any]) -> dict[str, Any]:
        args = GetPhysicalStockArgs.model_validate(arguments)
        request_id = self.request_id_factory()
        result = await self.wms_service.get_physical_stock(
            self.sap_config.connection_id,
            product=args.product,
            storage_bin=args.storage_bin,
            limit=args.limit,
            cursor=args.cursor,
            correlation_id=request_id,
        )
        return self._success(result, request_id)

    async def _list_orders_and_tasks(self, arguments: dict[str, Any]) -> dict[str, Any]:
        args = ListOrdersAndTasksArgs.model_validate(arguments)
        request_id = self.request_id_factory()
        result = await self.wms_service.list_orders_and_tasks(
            self.sap_config.connection_id,
            order_id=args.order_id,
            task_status=args.task_status,
            resource=args.resource,
            limit=args.limit,
            cursor=args.cursor,
            correlation_id=request_id,
        )
        return self._success(result, request_id)

    async def _assign_warehouse_order(
        self, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        args = AssignWarehouseOrderArgs.model_validate(arguments)
        request_id = self.request_id_factory()
        result = await self.wms_service.assign_warehouse_order(
            self.sap_config.connection_id,
            args.warehouse_order,
            args.resource,
            request_id,
        )
        return self._success(result, request_id)

    async def _confirm_warehouse_task(
        self, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        args = ConfirmWarehouseTaskArgs.model_validate(arguments)
        request_id = self.request_id_factory()
        result = await self.wms_service.confirm_warehouse_task(
            self.sap_config.connection_id,
            args.warehouse_task,
            args.warehouse_task_item,
            request_id,
        )
        return self._success(result, request_id)

    def _success(self, result: BaseModel, request_id: str) -> dict[str, Any]:
        return {
            "success": True,
            "data": result.model_dump(mode="json"),
            "source_system": "sap_ewm",
            "connection_id": self.sap_config.connection_id,
            "warehouse": self.sap_config.warehouse,
            "request_id": request_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


_sap_ewm_mcp_adapter: SAPEWMMCPAdapter | None = None


async def get_sap_ewm_mcp_adapter() -> SAPEWMMCPAdapter | None:
    """Return the enabled singleton without requiring config when disabled."""

    global _sap_ewm_mcp_adapter
    if os.getenv("SAP_EWM_ENABLED", "false").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return None
    if _sap_ewm_mcp_adapter is not None:
        return _sap_ewm_mcp_adapter

    sap_config = SAPEWMConfig.from_env()
    wms_service = await get_wms_service()
    adapter = SAPEWMMCPAdapter(SAPEWMMCPAdapterConfig(), sap_config, wms_service)
    if not await adapter.initialize():
        raise SAPEWMError(
            SAPEWMErrorCode.SAP_UNAVAILABLE,
            "SAP EWM adapter initialization failed",
        )
    _sap_ewm_mcp_adapter = adapter
    return adapter
