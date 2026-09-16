from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.api.domain.identity import IdentityContext
from src.api.services.mcp.gateway_v2 import MCPGatewayV2
from src.api.services.mcp.manifest_v2 import MCPToolManifestV2


def identity(scopes=("inventory.read",)):
    return IdentityContext(
        tenant_id="t1",
        user_id="u1",
        scopes=scopes,
        warehouse_scope=("WH-01",),
        authenticated_at=datetime.now(UTC),
    )


def manifest(mode="read"):
    return MCPToolManifestV2.create(
        tool_id="sap.stock.get",
        name="查询 SAP 库存",
        description="按仓库和 SKU 查询库存",
        provider_id="sap-ewm-mcp",
        capability="sap.ewm.stock.query",
        version="1.0.0",
        input_schema={
            "type": "object",
            "required": ["warehouse", "sku"],
            "properties": {
                "warehouse": {"type": "string"},
                "sku": {"type": "string"},
            },
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "required": ["quantity"],
            "properties": {"quantity": {"type": "integer"}},
        },
        required_scopes=("inventory.read",),
        risk_level="low" if mode == "read" else "high",
        read_write_mode=mode,
    )


@pytest.mark.asyncio
async def test_gateway_validates_scope_input_output_and_marks_result_untrusted() -> (
    None
):
    gateway = MCPGatewayV2()

    async def handler(arguments, context):
        assert context["tenant_id"] == "t1"
        return {"quantity": 12}

    gateway.register(manifest(), handler)

    result = await gateway.invoke(
        "sap.stock.get", {"warehouse": "WH-01", "sku": "SKU-1"}, identity()
    )

    assert result.data == {"quantity": 12}
    assert result.trust_level == "untrusted"
    assert result.schema_hash == manifest().schema_hash

    with pytest.raises(PermissionError):
        await gateway.invoke(
            "sap.stock.get", {"warehouse": "WH-01", "sku": "SKU-1"}, identity(())
        )
    with pytest.raises(ValueError, match="required"):
        await gateway.invoke("sap.stock.get", {"warehouse": "WH-01"}, identity())


@pytest.mark.asyncio
async def test_gateway_blocks_write_tools_in_agent_process() -> None:
    gateway = MCPGatewayV2()
    write_manifest = manifest("write")
    gateway.register(write_manifest, lambda arguments, context: {"quantity": 1})

    with pytest.raises(PermissionError, match="side effects"):
        await gateway.invoke(
            write_manifest.tool_id,
            {"warehouse": "WH-01", "sku": "SKU-1"},
            identity(),
        )
