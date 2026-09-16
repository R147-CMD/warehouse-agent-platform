"""Bridge existing local MCPAdapter tools into the governed V2 gateway."""

from __future__ import annotations

from typing import Any

from .base import MCPAdapter
from .gateway_v2 import MCPGatewayV2
from .manifest_v2 import MCPToolManifestV2

_DEFAULT_SCOPES = {
    "sap_ewm_get_physical_stock": ("inventory.read",),
    "sap_ewm_list_orders_and_tasks": ("operations.read",),
    "sap_ewm_assign_warehouse_order": ("sap.order.assign",),
    "sap_ewm_confirm_warehouse_task": ("sap.task.confirm",),
}

_DEFAULT_CAPABILITIES = {
    "sap_ewm_get_physical_stock": "sap.ewm.stock.query",
    "sap_ewm_list_orders_and_tasks": "sap.ewm.orders.query",
    "sap_ewm_assign_warehouse_order": "sap.ewm.order.assign",
    "sap_ewm_confirm_warehouse_task": "sap.ewm.task.confirm",
}


def register_legacy_adapter(
    gateway: MCPGatewayV2,
    adapter: MCPAdapter,
    *,
    provider_version: str = "1.0.0",
) -> None:
    for name, tool in adapter.tools.items():
        if tool.handler is None:
            continue
        metadata = tool.metadata or {}
        mutating = bool(metadata.get("mutating", not metadata.get("read_only", False)))
        manifest = MCPToolManifestV2.create(
            tool_id=name,
            name=name,
            description=tool.description,
            provider_id=adapter.config.name,
            capability=str(
                metadata.get("capability") or _DEFAULT_CAPABILITIES.get(name, name)
            ),
            version=str(metadata.get("version") or provider_version),
            input_schema=tool.parameters,
            output_schema={"type": "object"},
            required_scopes=tuple(
                metadata.get("required_scopes") or _DEFAULT_SCOPES.get(name, ())
            ),
            risk_level=str(
                metadata.get("risk_level") or ("high" if mutating else "low")
            ),
            read_write_mode="write" if mutating else "read",
            health_status="available" if adapter.connected else "degraded",
        )

        async def handler(
            arguments: dict[str, Any],
            _context: dict[str, Any],
            *,
            legacy_handler=tool.handler,
        ):
            return await legacy_handler(arguments)

        gateway.register(manifest, handler)
