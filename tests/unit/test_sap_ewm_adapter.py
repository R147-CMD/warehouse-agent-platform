"""Domain mapping and write-readback tests for SAPEWMAdapter."""

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.adapters.wms.base import InventoryItem, Task, TaskStatus, WMSDataError
from src.adapters.wms.sap_ewm import SAPEWMAdapter
from src.adapters.wms.sap_ewm_config import SAPEWMConfig
from src.adapters.wms.sap_ewm_errors import SAPEWMError, SAPEWMErrorCode
from src.adapters.wms.sap_ewm_http import SAPEWMODataClient


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


def stock_row() -> dict:
    return {
        "EWMWarehouse": "EW01",
        "Product": "TG11",
        "EWMStorageBin": "T010-02-05-A",
        "EWMStorageSection": "S001",
        "Batch": "",
        "EWMStockQuantityInBaseUnit": 956,
        "EWMStockQuantityBaseUnit": "EA",
        "StockItemUUID": "stock-uuid-1",
    }


def open_order(resource: str = "RES1", etag: str = 'W/"ORDER-1"') -> dict:
    return {
        "@odata.etag": etag,
        "EWMWarehouse": "EW01",
        "WarehouseOrder": "2000005003",
        "WarehouseOrderStatus": "O",
        "ExecutingResource": resource,
    }


def open_task(status: str = "O", etag: str = 'W/"TASK-1"') -> dict:
    return {
        "@odata.etag": etag,
        "EWMWarehouse": "EW01",
        "WarehouseTask": "1000004703",
        "WarehouseTaskItem": "0",
        "WarehouseOrder": "2000005003",
        "WarehouseTaskStatus": status,
        "Product": "TG11",
        "SourceStorageBin": "T010-02-05-A",
        "DestinationStorageBin": "GI-DOOR-01",
        "ExecutingResource": "RES1",
    }


@pytest.fixture
async def adapter_and_client():
    client = AsyncMock(spec=SAPEWMODataClient)
    client.connect.return_value = True
    client.close.return_value = None
    client.encode_next_link.return_value = None
    adapter = SAPEWMAdapter(sap_config(), client=client)
    assert await adapter.connect() is True
    return adapter, client


@pytest.mark.asyncio
async def test_maps_official_stock_fields(adapter_and_client) -> None:
    adapter, client = adapter_and_client
    client.get_collection.return_value = {"value": [stock_row()]}

    page = await adapter.get_physical_stock(
        product="O'Reilly-TG11", storage_bin="T010-02-05-A", limit=10
    )

    assert page.items[0].sku == "TG11"
    assert page.items[0].quantity == Decimal("956")
    assert page.items[0].batch is None
    params = client.get_collection.await_args.args[2]
    assert params == {
        "$filter": (
            "EWMWarehouse eq 'EW01' and Product eq 'O''Reilly-TG11' "
            "and EWMStorageBin eq 'T010-02-05-A'"
        ),
        "$top": "10",
    }


@pytest.mark.asyncio
async def test_stock_cursor_uses_validated_cursor_page(adapter_and_client) -> None:
    adapter, client = adapter_and_client
    client.get_cursor_page.return_value = {
        "value": [stock_row()],
        "@odata.nextLink": "http://sap.example.test/next",
    }
    client.encode_next_link.return_value = "cursor-2"

    page = await adapter.get_physical_stock(cursor="cursor-1")

    client.get_cursor_page.assert_awaited_once_with(
        "cursor-1", "stock", None
    )
    assert page.next_cursor == "cursor-2"


@pytest.mark.asyncio
async def test_maps_order_and_navigation_tasks(adapter_and_client) -> None:
    adapter, client = adapter_and_client
    client.get_entity.return_value = open_order()
    client.get_collection.return_value = {"value": [open_task()]}

    result = await adapter.list_orders_and_tasks(
        order_id="2000005003", task_status="O", resource="RES1", limit=20
    )

    assert result.orders[0].order_id == "2000005003"
    assert result.orders[0].etag == 'W/"ORDER-1"'
    assert result.orders[0].tasks[0].task_id == "1000004703"
    assert result.orders[0].tasks[0].source_bin == "T010-02-05-A"
    task_call = client.get_collection.await_args
    assert task_call.args[1].endswith("/_WarehouseTask")
    assert task_call.args[2] == {
        "$filter": (
            "WarehouseTaskStatus eq 'O' and ExecutingResource eq 'RES1'"
        ),
        "$top": "100",
    }


@pytest.mark.asyncio
async def test_assign_uses_current_etag(adapter_and_client) -> None:
    adapter, client = adapter_and_client
    client.get_entity.return_value = open_order()

    result = await adapter.assign_warehouse_order(
        "2000005003", "RES2", correlation_id="request-1"
    )

    client.post_action.assert_awaited_once_with(
        "orders",
        (
            "/WarehouseOrder(EWMWarehouse='EW01',"
            "WarehouseOrder='2000005003')/SAP__self.AssignWarehouseOrder"
        ),
        {"EWMResource": "RES2"},
        'W/"ORDER-1"',
        "request-1",
    )
    assert result.operation == "assign_warehouse_order"
    assert result.status == "ASSIGNED"
    assert result.outcome_confirmed_by_readback is False


@pytest.mark.asyncio
async def test_assign_timeout_is_confirmed_by_readback(
    adapter_and_client,
) -> None:
    adapter, client = adapter_and_client
    client.get_entity.side_effect = [open_order(), open_order(resource="RES2")]
    client.post_action.side_effect = SAPEWMError.unknown_outcome("timeout")

    result = await adapter.assign_warehouse_order("2000005003", "RES2")

    assert result.outcome_confirmed_by_readback is True
    assert client.get_entity.await_count == 2


@pytest.mark.asyncio
async def test_unverified_assign_timeout_remains_unknown(
    adapter_and_client,
) -> None:
    adapter, client = adapter_and_client
    client.get_entity.side_effect = [open_order(), open_order(resource="RES1")]
    client.post_action.side_effect = SAPEWMError.unknown_outcome("timeout")

    with pytest.raises(SAPEWMError) as captured:
        await adapter.assign_warehouse_order("2000005003", "RES2")

    assert captured.value.code is SAPEWMErrorCode.SAP_OUTCOME_UNKNOWN


@pytest.mark.asyncio
async def test_already_confirmed_task_is_idempotent(adapter_and_client) -> None:
    adapter, client = adapter_and_client
    client.get_entity.return_value = open_task(status="C")

    result = await adapter.confirm_warehouse_task_exact("1000004703", "0")

    client.post_action.assert_not_awaited()
    assert result.status == "CONFIRMED"
    assert result.outcome_confirmed_by_readback is True


@pytest.mark.asyncio
async def test_base_inventory_compatibility_delegates_to_stock(
    adapter_and_client,
) -> None:
    adapter, client = adapter_and_client
    client.get_collection.return_value = {"value": [stock_row()]}

    items = await adapter.get_inventory(location="T010-02-05-A", sku="TG11")

    assert items == [
        InventoryItem(
            sku="TG11",
            name="TG11",
            quantity=956,
            available_quantity=956,
            reserved_quantity=0,
            location="T010-02-05-A",
            zone="S001",
            lot_number=None,
            status="active",
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "argument"),
    [
        ("update_inventory", [InventoryItem(sku="TG11", name="TG11")]),
        (
            "create_task",
            Task(task_id="new", task_type=None),
        ),
    ],
)
async def test_unsupported_compatibility_writes_fail_explicitly(
    adapter_and_client, method_name: str, argument
) -> None:
    adapter, _client = adapter_and_client

    with pytest.raises(WMSDataError, match="not supported"):
        await getattr(adapter, method_name)(argument)


@pytest.mark.asyncio
async def test_disconnect_closes_odata_client(adapter_and_client) -> None:
    adapter, client = adapter_and_client

    assert await adapter.disconnect() is True

    client.close.assert_awaited_once()
    assert adapter.connected is False
