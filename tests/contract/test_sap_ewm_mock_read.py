"""Read-only OData V4 contract tests for the SAP EWM mock server."""

import pytest
from fastapi.testclient import TestClient

from src.mock_servers.sap_ewm.app import create_app


STOCK_ROOT = (
    "/sap/opu/odata4/sap/api_whse_physstockprod/srvd_a2x/"
    "sap/whsephysicalstockproducts/0001"
)
ORDER_ROOT = (
    "/sap/opu/odata4/sap/api_warehouse_order_task_2/srvd_a2x/"
    "sap/warehouseorder/0001"
)
BASIC_AUTH = ("mock-user", "mock-password")


@pytest.fixture
def mock_client() -> TestClient:
    with TestClient(create_app()) as client:
        yield client


def test_health_endpoint_is_available(mock_client: TestClient) -> None:
    response = mock_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "sap-ewm-mock"}


def test_get_stock_uses_odata_v4_shape(mock_client: TestClient) -> None:
    response = mock_client.get(
        STOCK_ROOT + "/WarehousePhysicalStockProducts",
        params={
            "$filter": "EWMWarehouse eq 'EW01' and Product eq 'TG11'",
            "$top": "1",
        },
        auth=BASIC_AUTH,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["@odata.context"].endswith(
        "$metadata#WarehousePhysicalStockProducts"
    )
    assert body["value"][0] == {
        "EWMWarehouse": "EW01",
        "Product": "TG11",
        "EWMStorageBin": "T010-02-05-A",
        "EWMStorageSection": "S001",
        "Batch": "",
        "EWMStockQuantityInBaseUnit": 956,
        "EWMStockQuantityBaseUnit": "EA",
        "StockItemUUID": "stock-uuid-1",
    }


def test_stock_pagination_returns_followable_next_link(
    mock_client: TestClient,
) -> None:
    response = mock_client.get(
        STOCK_ROOT + "/WarehousePhysicalStockProducts",
        params={"$filter": "EWMWarehouse eq 'EW01'", "$top": "1"},
        auth=BASIC_AUTH,
    )

    assert response.status_code == 200
    first = response.json()
    assert len(first["value"]) == 1
    assert first["@odata.nextLink"].startswith("http://testserver/")

    second = mock_client.get(first["@odata.nextLink"], auth=BASIC_AUTH)
    assert second.status_code == 200
    assert second.json()["value"][0]["StockItemUUID"] != first["value"][0][
        "StockItemUUID"
    ]


def test_malformed_filter_uses_odata_error_shape(mock_client: TestClient) -> None:
    response = mock_client.get(
        STOCK_ROOT + "/WarehousePhysicalStockProducts",
        params={"$filter": "Product ne 'TG11'"},
        auth=BASIC_AUTH,
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "INVALID_FILTER",
            "message": "Unsupported $filter expression",
        }
    }


@pytest.mark.parametrize(
    ("root", "required_properties"),
    [
        (STOCK_ROOT, ("EWMWarehouse", "Product", "StockItemUUID")),
        (ORDER_ROOT, ("WarehouseOrder", "WarehouseTask", "WarehouseTaskItem")),
    ],
)
def test_service_metadata_is_xml(
    mock_client: TestClient,
    root: str,
    required_properties: tuple[str, ...],
) -> None:
    response = mock_client.get(root + "/$metadata", auth=BASIC_AUTH)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert "edmx:Edmx" in response.text
    for property_name in required_properties:
        assert f'Name="{property_name}"' in response.text


def test_get_orders_and_single_order_etag(mock_client: TestClient) -> None:
    collection = mock_client.get(
        ORDER_ROOT + "/WarehouseOrder",
        params={"$filter": "EWMWarehouse eq 'EW01'"},
        auth=BASIC_AUTH,
    )

    assert collection.status_code == 200
    assert [row["WarehouseOrder"] for row in collection.json()["value"]] == [
        "2000005003",
        "2000005004",
    ]

    entity = mock_client.get(
        ORDER_ROOT
        + "/WarehouseOrder(EWMWarehouse='EW01',WarehouseOrder='2000005003')",
        auth=BASIC_AUTH,
    )
    assert entity.status_code == 200
    assert entity.json()["ExecutingResource"] == "RES1"
    assert entity.json()["@odata.etag"] == 'W/"MOCK-2000005003-1"'


def test_get_order_tasks_navigation(mock_client: TestClient) -> None:
    response = mock_client.get(
        ORDER_ROOT
        + "/WarehouseOrder(EWMWarehouse='EW01',WarehouseOrder='2000005003')"
        "/_WarehouseTask",
        auth=BASIC_AUTH,
    )

    assert response.status_code == 200
    task = response.json()["value"][0]
    assert task["WarehouseOrder"] == "2000005003"
    assert task["WarehouseTask"] == "1000004703"
    assert task["WarehouseTaskStatus"] == "O"


def test_get_single_task_and_missing_entity(mock_client: TestClient) -> None:
    response = mock_client.get(
        ORDER_ROOT
        + "/WarehouseTask(EWMWarehouse='EW01',WarehouseTask='1000004703',"
        "WarehouseTaskItem='0')",
        auth=BASIC_AUTH,
    )
    missing = mock_client.get(
        ORDER_ROOT
        + "/WarehouseTask(EWMWarehouse='EW01',WarehouseTask='9999999999',"
        "WarehouseTaskItem='0')",
        auth=BASIC_AUTH,
    )

    assert response.status_code == 200
    assert response.json()["Product"] == "TG11"
    assert response.json()["@odata.etag"] == 'W/"MOCK-1000004703-0-1"'
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "ENTITY_NOT_FOUND"
