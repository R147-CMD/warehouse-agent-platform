"""Routing tests for the SAP EWM MCP tools exposed to the operations agent."""

from unittest.mock import AsyncMock

import pytest

from src.api.agents.operations.mcp_operations_agent import (
    MCPOperationsCoordinationAgent,
    MCPOperationsQuery,
)
from src.api.routers.mcp import _register_mcp_adapters
from src.api.services.mcp.tool_discovery import DiscoveredTool, ToolCategory

SAP_TOOL_SCHEMAS = {
    "sap_ewm_get_physical_stock": {
        "product": {"type": ["string", "null"]},
        "storage_bin": {"type": ["string", "null"]},
        "limit": {"type": "integer"},
        "cursor": {"type": ["string", "null"]},
    },
    "sap_ewm_list_orders_and_tasks": {
        "order_id": {"type": ["string", "null"]},
        "task_status": {"type": ["string", "null"]},
        "resource": {"type": ["string", "null"]},
        "limit": {"type": "integer"},
        "cursor": {"type": ["string", "null"]},
    },
    "sap_ewm_assign_warehouse_order": {
        "warehouse_order": {"type": "string"},
        "resource": {"type": "string"},
        "reason": {"type": "string"},
    },
    "sap_ewm_confirm_warehouse_task": {
        "warehouse_task": {"type": "string"},
        "warehouse_task_item": {"type": "string", "default": "0"},
        "reason": {"type": "string"},
    },
}


def _sap_tools() -> list[DiscoveredTool]:
    return [
        DiscoveredTool(
            name=name,
            description=f"SAP EWM tool {name}",
            category=ToolCategory.OPERATIONS,
            source="sap_ewm_tools",
            source_type="mcp_adapter",
            parameters={"type": "object", "properties": properties},
            tool_id=f"tool-{name}",
        )
        for name, properties in SAP_TOOL_SCHEMAS.items()
    ]


@pytest.mark.asyncio
async def test_global_registry_registers_enabled_sap_adapter(monkeypatch) -> None:
    from src.api.services.mcp.adapters import equipment_adapter
    from src.api.services.mcp.adapters import forecasting_adapter
    from src.api.services.mcp.adapters import operations_adapter
    from src.api.services.mcp.adapters import safety_adapter
    from src.api.services.mcp.adapters import sap_ewm_adapter

    monkeypatch.setattr(
        equipment_adapter, "get_equipment_adapter", AsyncMock(return_value=object())
    )
    monkeypatch.setattr(
        operations_adapter, "get_operations_adapter", AsyncMock(return_value=object())
    )
    monkeypatch.setattr(
        safety_adapter, "get_safety_adapter", AsyncMock(return_value=object())
    )
    monkeypatch.setattr(
        forecasting_adapter,
        "get_forecasting_adapter",
        AsyncMock(return_value=object()),
    )
    sap_adapter = object()
    monkeypatch.setattr(
        sap_ewm_adapter,
        "get_sap_ewm_mcp_adapter",
        AsyncMock(return_value=sap_adapter),
    )
    discovery = AsyncMock()

    await _register_mcp_adapters(discovery)

    assert (
        "sap_ewm_tools",
        sap_adapter,
        "mcp_adapter",
    ) in [call.args for call in discovery.register_discovery_source.await_args_list]


@pytest.mark.asyncio
async def test_agent_registry_skips_disabled_sap_adapter(monkeypatch) -> None:
    from src.api.services.mcp.adapters import equipment_adapter
    from src.api.services.mcp.adapters import operations_adapter
    from src.api.services.mcp.adapters import sap_ewm_adapter

    monkeypatch.setattr(
        equipment_adapter, "get_equipment_adapter", AsyncMock(return_value=object())
    )
    monkeypatch.setattr(
        operations_adapter, "get_operations_adapter", AsyncMock(return_value=object())
    )
    monkeypatch.setattr(
        sap_ewm_adapter,
        "get_sap_ewm_mcp_adapter",
        AsyncMock(return_value=None),
    )
    agent = MCPOperationsCoordinationAgent()
    agent.tool_discovery = AsyncMock()

    await agent._register_mcp_sources()

    sources = [
        call.args[0]
        for call in agent.tool_discovery.register_discovery_source.await_args_list
    ]
    assert "sap_ewm_tools" not in sources


@pytest.mark.asyncio
async def test_agent_registry_registers_enabled_sap_adapter(monkeypatch) -> None:
    from src.api.services.mcp.adapters import equipment_adapter
    from src.api.services.mcp.adapters import operations_adapter
    from src.api.services.mcp.adapters import sap_ewm_adapter

    monkeypatch.setattr(
        equipment_adapter, "get_equipment_adapter", AsyncMock(return_value=object())
    )
    monkeypatch.setattr(
        operations_adapter, "get_operations_adapter", AsyncMock(return_value=object())
    )
    sap_adapter = object()
    monkeypatch.setattr(
        sap_ewm_adapter,
        "get_sap_ewm_mcp_adapter",
        AsyncMock(return_value=sap_adapter),
    )
    agent = MCPOperationsCoordinationAgent()
    agent.tool_discovery = AsyncMock()

    await agent._register_mcp_sources()

    assert (
        "sap_ewm_tools",
        sap_adapter,
        "mcp_adapter",
    ) in [
        call.args
        for call in agent.tool_discovery.register_discovery_source.await_args_list
    ]


@pytest.mark.asyncio
async def test_sap_intent_discovers_the_whole_sap_source() -> None:
    tools = _sap_tools()
    agent = MCPOperationsCoordinationAgent()
    agent.tool_discovery = AsyncMock()
    agent.tool_discovery.get_tools_by_source.return_value = tools

    result = await agent._discover_relevant_tools(
        MCPOperationsQuery(
            intent="sap_stock_query",
            entities={"product": "TG11"},
            context={},
            user_query="Show SAP stock for TG11",
        )
    )

    assert result == tools
    agent.tool_discovery.get_tools_by_source.assert_awaited_once_with("sap_ewm_tools")
    agent.tool_discovery.get_tools_by_category.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("intent", "entities", "expected_tool", "expected_arguments"),
    [
        (
            "sap_stock_query",
            {"product": "TG11", "storage_bin": "T010-02-05-A"},
            "sap_ewm_get_physical_stock",
            {"product": "TG11", "storage_bin": "T010-02-05-A"},
        ),
        (
            "sap_order_task_query",
            {
                "warehouse_order": "2000005003",
                "task_status": "O",
                "resource": "RES1",
            },
            "sap_ewm_list_orders_and_tasks",
            {"order_id": "2000005003", "task_status": "O", "resource": "RES1"},
        ),
        (
            "sap_order_assignment",
            {"warehouse_order": "2000005003", "resource": "RES2"},
            "sap_ewm_assign_warehouse_order",
            {
                "warehouse_order": "2000005003",
                "resource": "RES2",
                "reason": "Assign order 2000005003 to RES2 'now'",
            },
        ),
        (
            "sap_task_confirmation",
            {"warehouse_task": "1000004703"},
            "sap_ewm_confirm_warehouse_task",
            {
                "warehouse_task": "1000004703",
                "warehouse_task_item": "0",
                "reason": "Confirm task 1000004703",
            },
        ),
    ],
)
async def test_sap_intent_creates_exactly_one_typed_step(
    intent: str,
    entities: dict[str, object],
    expected_tool: str,
    expected_arguments: dict[str, object],
) -> None:
    user_query = {
        "sap_order_assignment": "Assign order 2000005003 to RES2 `now`\n",
        "sap_task_confirmation": "Confirm task 1000004703",
    }.get(intent, "Query SAP EWM")
    query = MCPOperationsQuery(
        intent=intent,
        entities=entities,
        context={},
        user_query=user_query,
    )
    agent = MCPOperationsCoordinationAgent()

    plan = await agent._create_tool_execution_plan(query, _sap_tools())

    assert len(plan) == 1
    assert plan[0]["tool_name"] == expected_tool
    assert plan[0]["arguments"] == expected_arguments
    assert plan[0]["required"] is True


@pytest.mark.asyncio
async def test_operations_parser_advertises_sap_intents() -> None:
    agent = MCPOperationsCoordinationAgent()
    agent.nim_client = AsyncMock()
    agent.nim_client.generate_response.return_value.content = (
        '{"intent":"sap_stock_query","entities":{"product":"TG11"},' '"context":{}}'
    )

    parsed = await agent._parse_operations_query("Show SAP stock for TG11", None)

    system_prompt = agent.nim_client.generate_response.await_args.args[0][0]["content"]
    assert "sap_stock_query" in system_prompt
    assert "sap_order_task_query" in system_prompt
    assert "sap_order_assignment" in system_prompt
    assert "sap_task_confirmation" in system_prompt
    assert parsed.intent == "sap_stock_query"
