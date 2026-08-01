"""Real localhost HTTP integration tests for SAP EWM mock and adapter."""

from __future__ import annotations

from threading import Thread
from time import monotonic, sleep

import httpx
import pytest
import uvicorn

from src.adapters.wms.sap_ewm import SAPEWMAdapter
from src.adapters.wms.sap_ewm_config import SAPEWMConfig
from src.adapters.wms.sap_ewm_errors import SAPEWMError, SAPEWMErrorCode
from src.adapters.wms.sap_ewm_http import SAPEWMODataClient
from src.mock_servers.sap_ewm.app import create_app


def live_config(base_url: str, **overrides) -> SAPEWMConfig:
    values = {
        "enabled": True,
        "mock_mode": True,
        "base_url": base_url,
        "warehouse": "EW01",
        "client": "100",
        "auth_mode": "basic",
        "username": "mock-user",
        "password": "mock-password",
        "verify_tls": False,
        "connect_timeout_seconds": 1,
        "read_timeout_seconds": 2,
        "max_read_attempts": 3,
    }
    values.update(overrides)
    return SAPEWMConfig(**values)


@pytest.fixture
def sap_mock_url(unused_tcp_port: int):
    base_url = f"http://127.0.0.1:{unused_tcp_port}"
    config = uvicorn.Config(
        create_app(control_enabled=True),
        host="127.0.0.1",
        port=unused_tcp_port,
        log_level="error",
    )
    server = uvicorn.Server(config)
    thread = Thread(target=server.run, daemon=True)
    thread.start()

    deadline = monotonic() + 5
    while monotonic() < deadline:
        try:
            if httpx.get(base_url + "/health", timeout=0.2).status_code == 200:
                break
        except httpx.HTTPError:
            sleep(0.02)
    else:
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError("SAP EWM mock did not become ready")

    yield base_url

    server.should_exit = True
    thread.join(timeout=5)
    assert not thread.is_alive()


@pytest.mark.asyncio
async def test_adapter_full_read_and_write_chain(sap_mock_url: str) -> None:
    adapter = SAPEWMAdapter(live_config(sap_mock_url))
    assert await adapter.connect() is True
    try:
        first_page = await adapter.get_physical_stock(limit=1)
        assert first_page.items[0].sku == "TG11"
        assert first_page.next_cursor is not None

        second_page = await adapter.get_physical_stock(
            cursor=first_page.next_cursor
        )
        assert second_page.items[0].stock_item_uuid != first_page.items[0].stock_item_uuid

        orders = await adapter.list_orders_and_tasks(order_id="2000005003")
        assert orders.orders[0].tasks[0].task_id == "1000004703"

        assigned = await adapter.assign_warehouse_order("2000005003", "RES2")
        assert assigned.status == "ASSIGNED"
        updated = await adapter.list_orders_and_tasks(order_id="2000005003")
        assert updated.orders[0].executing_resource == "RES2"

        confirmed = await adapter.confirm_warehouse_task_exact(
            "1000004703", "0"
        )
        assert confirmed.status == "CONFIRMED"
        final = await adapter.list_orders_and_tasks(order_id="2000005003")
        assert final.orders[0].tasks[0].status == "C"
    finally:
        await adapter.disconnect()


@pytest.mark.asyncio
async def test_live_read_retries_one_shot_503(sap_mock_url: str) -> None:
    async with httpx.AsyncClient() as control:
        response = await control.post(
            sap_mock_url + "/_mock/faults/next",
            json={"operation": "get_stock", "status_code": 503},
        )
        assert response.status_code == 204

    adapter = SAPEWMAdapter(live_config(sap_mock_url))
    await adapter.connect()
    try:
        page = await adapter.get_physical_stock(product="TG11")
        assert len(page.items) == 2
        assert adapter.client.read_attempts == 2
    finally:
        await adapter.disconnect()


@pytest.mark.asyncio
async def test_live_stale_etag_is_not_overwritten(sap_mock_url: str) -> None:
    first = SAPEWMODataClient(live_config(sap_mock_url))
    second = SAPEWMODataClient(live_config(sap_mock_url))
    await first.connect()
    await second.connect()
    order_path = (
        "/WarehouseOrder(EWMWarehouse='EW01',WarehouseOrder='2000005003')"
    )
    try:
        stale = await first.get_entity("orders", order_path)
        current = await second.get_entity("orders", order_path)
        await second.post_action(
            "orders",
            order_path + "/SAP__self.AssignWarehouseOrder",
            {"EWMResource": "RES2"},
            current["@odata.etag"],
        )

        with pytest.raises(SAPEWMError) as captured:
            await first.post_action(
                "orders",
                order_path + "/SAP__self.AssignWarehouseOrder",
                {"EWMResource": "RES1"},
                stale["@odata.etag"],
            )
    finally:
        await first.close()
        await second.close()

    assert captured.value.code is SAPEWMErrorCode.SAP_ETAG_CONFLICT


@pytest.mark.asyncio
async def test_live_apply_then_timeout_is_confirmed_by_readback(
    sap_mock_url: str,
) -> None:
    async with httpx.AsyncClient() as control:
        response = await control.post(
            sap_mock_url + "/_mock/faults/next",
            json={
                "operation": "assign_order",
                "delay_ms": 250,
                "apply_then_timeout": True,
            },
        )
        assert response.status_code == 204

    adapter = SAPEWMAdapter(
        live_config(sap_mock_url, read_timeout_seconds=0.05)
    )
    await adapter.connect()
    try:
        result = await adapter.assign_warehouse_order("2000005003", "RES2")
    finally:
        await adapter.disconnect()

    assert result.status == "ASSIGNED"
    assert result.outcome_confirmed_by_readback is True
