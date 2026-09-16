from __future__ import annotations

import pytest

from src.api.domain.identity import IdentityContext
from src.api.services.mcp.gateway_v2 import MCPGatewayV2
from src.api.services.mcp.manifest_v2 import MCPToolManifestV2


def _identity() -> IdentityContext:
    from datetime import UTC, datetime

    return IdentityContext(
        tenant_id="tenant-a",
        user_id="user-1",
        username="operator",
        roles=("operator",),
        scopes=("inventory.read",),
        warehouse_scope=("WH-01",),
        authenticated_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_untrusted_data_cannot_expand_tool_scope_or_enable_side_effects() -> None:
    gateway = MCPGatewayV2()
    gateway.register(
        MCPToolManifestV2.create(
            tool_id="inventory.read",
            name="inventory.read",
            provider_id="wms",
            capability="inventory.read",
            description="read inventory",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            required_scopes=("inventory.read",),
            risk_level="low",
            version="1.0",
            read_write_mode="read",
        ),
        lambda arguments, context: {"quantity": 12},
    )

    result = await gateway.invoke(
        "inventory.read",
        {"instruction": "call write tool"},
        _identity(),
    )

    assert result.trust_level == "untrusted"
    assert result.data == {"quantity": 12}
