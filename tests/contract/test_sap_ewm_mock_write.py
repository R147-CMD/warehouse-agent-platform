"""Authentication and write-protocol contracts for the SAP EWM mock."""

from time import monotonic

import pytest
from fastapi.testclient import TestClient

from src.mock_servers.sap_ewm.app import create_app


ORDER_ROOT = (
    "/sap/opu/odata4/sap/api_warehouse_order_task_2/srvd_a2x/"
    "sap/warehouseorder/0001"
)
STOCK_PATH = (
    "/sap/opu/odata4/sap/api_whse_physstockprod/srvd_a2x/"
    "sap/whsephysicalstockproducts/0001/WarehousePhysicalStockProducts"
)
BASIC_AUTH = ("mock-user", "mock-password")


@pytest.fixture
def mock_client(monkeypatch) -> TestClient:
    monkeypatch.setenv("SAP_EWM_MOCK_CONTROL_ENABLED", "true")
    with TestClient(create_app()) as client:
        yield client


def order_path(order_id: str) -> str:
    return (
        ORDER_ROOT
        + f"/WarehouseOrder(EWMWarehouse='EW01',WarehouseOrder='{order_id}')"
    )


def assign_path(order_id: str) -> str:
    return order_path(order_id) + "/SAP__self.AssignWarehouseOrder"


def task_path(task_id: str, item: str = "0") -> str:
    return (
        ORDER_ROOT
        + f"/WarehouseTask(EWMWarehouse='EW01',WarehouseTask='{task_id}',"
        f"WarehouseTaskItem='{item}')"
    )


def confirm_path(task_id: str, item: str = "0") -> str:
    return task_path(task_id, item) + "/SAP__self.ConfirmWarehouseTaskExact"


def get_order(client: TestClient, order_id: str) -> dict:
    response = client.get(order_path(order_id), auth=BASIC_AUTH)
    assert response.status_code == 200
    return response.json()


def get_task(client: TestClient, task_id: str, item: str = "0") -> dict:
    response = client.get(task_path(task_id, item), auth=BASIC_AUTH)
    assert response.status_code == 200
    return response.json()


def fetch_csrf(client: TestClient) -> str:
    response = client.get(
        ORDER_ROOT + "/$metadata",
        headers={"X-CSRF-Token": "Fetch"},
        auth=BASIC_AUTH,
    )
    assert response.status_code == 200
    assert response.cookies.get("SAP_SESSIONID_MOCK")
    return response.headers["X-CSRF-Token"]


def write_headers(client: TestClient, etag: str) -> dict[str, str]:
    return {"X-CSRF-Token": fetch_csrf(client), "If-Match": etag}


def test_business_routes_require_authentication(mock_client: TestClient) -> None:
    response = mock_client.get(STOCK_PATH)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    assert response.headers["www-authenticate"] == "Basic realm=\"SAP EWM Mock\""


def test_oauth_client_credentials_can_access_business_routes(
    mock_client: TestClient,
) -> None:
    token_response = mock_client.post(
        "/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": "mock-client",
            "client_secret": "mock-secret",
        },
    )

    assert token_response.status_code == 200
    token = token_response.json()["access_token"]
    response = mock_client.get(
        STOCK_PATH,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200


def test_assign_requires_csrf_and_etag(mock_client: TestClient) -> None:
    no_csrf = mock_client.post(
        assign_path("2000005003"),
        json={"EWMResource": "RES2"},
        auth=BASIC_AUTH,
    )
    token = fetch_csrf(mock_client)
    no_etag = mock_client.post(
        assign_path("2000005003"),
        json={"EWMResource": "RES2"},
        headers={"X-CSRF-Token": token},
        auth=BASIC_AUTH,
    )

    assert no_csrf.status_code == 403
    assert no_csrf.json()["error"]["code"] == "CSRF_TOKEN_MISSING"
    assert no_etag.status_code == 428
    assert no_etag.json()["error"]["code"] == "ETAG_REQUIRED"


def test_assign_changes_resource_and_etag(mock_client: TestClient) -> None:
    order = get_order(mock_client, "2000005003")
    response = mock_client.post(
        assign_path("2000005003"),
        json={"EWMResource": "RES2"},
        headers=write_headers(mock_client, order["@odata.etag"]),
        auth=BASIC_AUTH,
    )

    assert response.status_code == 204
    updated = get_order(mock_client, "2000005003")
    assert updated["ExecutingResource"] == "RES2"
    assert updated["@odata.etag"] != order["@odata.etag"]


def test_stale_etag_and_unknown_resource_are_business_errors(
    mock_client: TestClient,
) -> None:
    order = get_order(mock_client, "2000005003")
    stale = mock_client.post(
        assign_path("2000005003"),
        json={"EWMResource": "RES2"},
        headers=write_headers(mock_client, 'W/"STALE"'),
        auth=BASIC_AUTH,
    )
    unknown_resource = mock_client.post(
        assign_path("2000005003"),
        json={"EWMResource": "UNKNOWN"},
        headers=write_headers(mock_client, order["@odata.etag"]),
        auth=BASIC_AUTH,
    )

    assert stale.status_code == 412
    assert stale.json()["error"]["code"] == "ETAG_MISMATCH"
    assert unknown_resource.status_code == 409
    assert unknown_resource.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_confirm_exact_changes_task_status(mock_client: TestClient) -> None:
    task = get_task(mock_client, "1000004703")
    response = mock_client.post(
        confirm_path("1000004703"),
        json={},
        headers=write_headers(mock_client, task["@odata.etag"]),
        auth=BASIC_AUTH,
    )

    assert response.status_code == 204
    updated = get_task(mock_client, "1000004703")
    assert updated["WarehouseTaskStatus"] == "C"
    assert updated["@odata.etag"] != task["@odata.etag"]


def test_missing_write_entity_returns_404(mock_client: TestClient) -> None:
    response = mock_client.post(
        confirm_path("9999999999"),
        json={},
        headers=write_headers(mock_client, 'W/"MISSING"'),
        auth=BASIC_AUTH,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ENTITY_NOT_FOUND"


@pytest.mark.parametrize("status_code", [429, 500])
def test_fault_status_is_one_shot(
    mock_client: TestClient, status_code: int
) -> None:
    configured = mock_client.post(
        "/_mock/faults/next",
        json={"operation": "get_stock", "status_code": status_code},
    )
    first = mock_client.get(STOCK_PATH, auth=BASIC_AUTH)
    second = mock_client.get(STOCK_PATH, auth=BASIC_AUTH)

    assert configured.status_code == 204
    assert first.status_code == status_code
    assert first.json()["error"]["code"] == f"MOCK_FAULT_{status_code}"
    assert second.status_code == 200


def test_fault_delay_is_applied_once(mock_client: TestClient) -> None:
    mock_client.post(
        "/_mock/faults/next",
        json={"operation": "get_stock", "delay_ms": 30},
    )

    started = monotonic()
    response = mock_client.get(STOCK_PATH, auth=BASIC_AUTH)
    elapsed = monotonic() - started

    assert response.status_code == 200
    assert elapsed >= 0.025


def test_apply_then_timeout_changes_state(mock_client: TestClient) -> None:
    order = get_order(mock_client, "2000005003")
    mock_client.post(
        "/_mock/faults/next",
        json={
            "operation": "assign_order",
            "delay_ms": 20,
            "apply_then_timeout": True,
        },
    )

    response = mock_client.post(
        assign_path("2000005003"),
        json={"EWMResource": "RES2"},
        headers=write_headers(mock_client, order["@odata.etag"]),
        auth=BASIC_AUTH,
    )

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "MOCK_APPLY_THEN_TIMEOUT"
    assert get_order(mock_client, "2000005003")["ExecutingResource"] == "RES2"


def test_reset_restores_seed_state_and_request_counts(
    mock_client: TestClient,
) -> None:
    order = get_order(mock_client, "2000005003")
    mock_client.post(
        assign_path("2000005003"),
        json={"EWMResource": "RES2"},
        headers=write_headers(mock_client, order["@odata.etag"]),
        auth=BASIC_AUTH,
    )
    counts = mock_client.get("/_mock/requests").json()

    assert counts["assign_order"] == 1
    assert mock_client.post("/_mock/reset").status_code == 204
    assert get_order(mock_client, "2000005003")["ExecutingResource"] == "RES1"


def test_control_routes_are_hidden_when_disabled() -> None:
    with TestClient(create_app(control_enabled=False)) as client:
        response = client.post(
            "/_mock/faults/next",
            json={"operation": "get_stock", "status_code": 500},
        )

    assert response.status_code == 404
