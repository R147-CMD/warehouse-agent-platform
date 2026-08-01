"""Tests for preserving MCP tool risk metadata across discovery."""

from unittest.mock import AsyncMock

import pytest

from src.api.services.approval.policy import ApprovalPolicy
from src.api.services.mcp.base import (
    AdapterConfig,
    AdapterType,
    MCPAdapter,
    ToolCategory,
    ToolConfig,
)
from src.api.services.mcp.tool_discovery import ToolDiscoveryService


class FakeAdapter(MCPAdapter):
    """Minimal real MCP adapter used to exercise the discovery boundary."""

    def __init__(self) -> None:
        super().__init__(
            AdapterConfig(name="sap_ewm_tools", adapter_type=AdapterType.WMS)
        )

    async def initialize(self) -> bool:
        return True

    async def connect(self) -> bool:
        return True

    async def disconnect(self) -> bool:
        return True

    async def health_check(self) -> dict[str, str]:
        return {"status": "healthy"}


async def discover_fake_tool(
    name: str, metadata: dict[str, bool]
):
    adapter = FakeAdapter()
    added = adapter.add_tool(
        ToolConfig(
            name=name,
            description=f"SAP EWM tool: {name}",
            category=ToolCategory.DATA_ACCESS,
            parameters={"type": "object", "properties": {}},
            handler=AsyncMock(),
            metadata=metadata,
        )
    )
    assert added is True

    discovery = ToolDiscoveryService()
    await discovery.register_discovery_source(
        "sap_ewm_tools", adapter, "mcp_adapter"
    )
    assert await discovery.discover_tools_from_source("sap_ewm_tools") == 1

    return next(
        tool for tool in discovery.discovered_tools.values() if tool.name == name
    )


@pytest.mark.asyncio
async def test_discovery_preserves_read_only_metadata() -> None:
    """Dropping read_only metadata must not turn a proven read into an approval."""

    tool = await discover_fake_tool(
        "sap_ewm_get_physical_stock",
        {"read_only": True, "requires_approval": False},
    )

    assert tool.metadata["read_only"] is True
    assert tool.metadata["requires_approval"] is False
    assert ApprovalPolicy().requires_approval(tool) is False


@pytest.mark.asyncio
async def test_discovery_preserves_mutating_metadata() -> None:
    """Dropping mutating metadata must not weaken an explicitly risky tool."""

    tool = await discover_fake_tool(
        "sap_ewm_confirm_warehouse_task",
        {"mutating": True, "requires_approval": True},
    )

    assert tool.metadata["mutating"] is True
    assert tool.metadata["requires_approval"] is True
    assert ApprovalPolicy().requires_approval(tool) is True
